#!/bin/bash
# Keep ~/.claude/skills in sync with the platform-skills catalog on mctl-gitops main.
#
# Why a dedicated mirror: ~/.claude/skills used to symlink straight into the
# working checkout at ~/PycharmProjects/mctlhq/mctl-gitops. That checkout is
# shared with concurrent agents and routinely sits on a feature branch with
# uncommitted changes, so the skills Claude loaded were whatever branch someone
# left it on. On 2026-08-31 that silently served a review-watch from before the
# quota fix, hours after the fix was published to main.
#
# This mirror is checked out on main, sparse to the catalog, and never edited by
# hand -- skill edits go through the mctl_publish_platform_skill MCP tool, which
# commits to main, and land here on the next run.
set -uo pipefail
shopt -s nullglob   # пустой каталог не должен давать литерал "*" в цикле


# Под launchd нет TTY: запрос пароля к ключу или неизвестный host key повесили бы
# fetch навсегда, причём с захваченным локом. Пусть лучше сразу падает.
# Без таймаутов повисший ssh держал бы лок бесконечно, и kill -0 считал бы его
# живым: каждый следующий тик молча пропускал бы синк.
export GIT_SSH_COMMAND="${GIT_SSH_COMMAND:-ssh -o BatchMode=yes -o ConnectTimeout=15 -o ServerAliveInterval=15 -o ServerAliveCountMax=3}"

REMOTE="git@github.com:mctlhq/mctl-gitops.git"
MIRROR="$HOME/.claude/skills-catalog"
CATALOG="$MIRROR/platform-gitops/platform-skills/catalog"
SKILLS="$HOME/.claude/skills"
LOG="$HOME/.claude/skills-sync.log"
# Коммит, для которого реконсиляция ДОШЛА ДО КОНЦА. Флага в памяти не хватало:
# прогон, убитый после ресета зеркала, но до инвалидации кеша, оставлял
# следующему прогону BEFORE == AFTER, и протухший watcher жил дальше.
STATE="$HOME/.claude/skills-sync.state"

exec >>"$LOG" 2>&1

# launchd запускает нас каждые 15 мин, а README предлагает и ручной запуск.
# Два одновременных прогона дерутся за один git-репозиторий (index.lock), а в
# худшем случае один делает rm -rf зеркала, пока другой в нём checkout'ится.
# mkdir атомарен; flock(1) на macOS нет.
LOCK="$HOME/.claude/skills-sync.lock"
# Возраст лока. stat(1) несовместим между BSD и GNU, поэтому пробуем оба; при
# неудаче возвращаем 0, то есть "свежий" -- лучше пропустить прогон, чем увести
# лок у живого процесса.
lock_age_seconds() {
  local m
  m=$(stat -f %m "$LOCK" 2>/dev/null) || m=$(stat -c %Y "$LOCK" 2>/dev/null) || m=""
  [ -n "$m" ] || { echo 0; return; }
  echo $(( $(date +%s) - m ))
}
if ! mkdir "$LOCK" 2>/dev/null; then
  STALE=""
  HELD=$(cat "$LOCK/pid" 2>/dev/null)
  if [ -n "$HELD" ]; then
    kill -0 "$HELD" 2>/dev/null || STALE="pid $HELD мёртв"
  elif [ "$(lock_age_seconds)" -gt 60 ]; then
    # Пустой или отсутствующий pid-файл: свежий -- значит другой процесс прямо
    # сейчас между созданием файла и записью pid, трогать нельзя. Старый --
    # значит его убили в этом окне, и лок надо забрать, иначе он вечен.
    # Убитый между mkdir и записью pid оставлял лок без pid-файла, и он залипал
    # навсегда. Возраст различает это от нормального прогона, который окно между
    # mkdir и записью проходит за микросекунды, а сам живёт секунды.
    STALE="без живого pid и старше минуты"
  fi
  if [ -n "$STALE" ]; then
    # Два прогона могут одновременно счесть лок стухшим; без атомарного шага
    # второй снёс бы уже созданный локом первого каталог. Переименование
    # выигрывает ровно один процесс.
    echo "[$(date -u +%FT%TZ)] снимаю осиротевший лок ($STALE)"
    TAKEN="$LOCK.stale.$$"
    mv "$LOCK" "$TAKEN" 2>/dev/null || { echo "  перехват достался другому прогону -- выхожу"; exit 0; }
    rm -rf "$TAKEN"
    mkdir "$LOCK" 2>/dev/null || { echo "  лок занят -- выхожу"; exit 0; }
  else
    echo "[$(date -u +%FT%TZ)] синк уже идёт -- выхожу"; exit 0
  fi
fi
# Метка владельца: если наш лок кто-то перехватил как стухший, мы не должны
# снести уже чужой каталог своим trap'ом.
OWNER="$$-$(date +%s)-$RANDOM"
# noclobber: если машина уснула между mkdir и этой строкой, лок мог быть уже
# перехвачен как стухший -- тогда файлы существуют и перезаписывать их нельзя.
set -C
if ! echo "$OWNER" > "$LOCK/owner" 2>/dev/null; then
  set +C; echo "  лок перехвачен, пока мы спали -- выхожу"; exit 0
fi
set +C
echo $$ > "$LOCK/pid"
trap '[ "$(cat "$LOCK/owner" 2>/dev/null)" = "$OWNER" ] && rm -rf "$LOCK"' EXIT

echo "[$(date -u +%FT%TZ)] sync start"

MIRROR_OK=0
if [ -d "$MIRROR/.git" ] \
   && git -C "$MIRROR" rev-parse --verify --quiet HEAD >/dev/null 2>&1 \
   && [ "$(git -C "$MIRROR" config --get remote.origin.url 2>/dev/null)" = "$REMOTE" ]; then
  MIRROR_OK=1
fi
# Клон, оборванный после создания .git, но до настройки remote/ref'ов, иначе
# считался бы валидным зеркалом вечно: fetch падал бы каждый раз, а само
# зеркало никогда не пересоздавалось.
if [ "$MIRROR_OK" = "0" ]; then
  echo "  зеркало отсутствует или непригодно ($MIRROR) -- пересоздаю"
  rm -rf "$MIRROR"
  git clone --filter=blob:none --no-checkout --single-branch --branch main \
    "$REMOTE" "$MIRROR" || { echo "  clone FAILED"; exit 1; }
  git -C "$MIRROR" sparse-checkout set --cone platform-gitops/platform-skills/catalog \
    || { echo "  sparse-checkout FAILED -- иначе checkout вытянул бы весь репозиторий"; exit 1; }
  git -C "$MIRROR" checkout main || { echo "  checkout FAILED"; exit 1; }
fi

BEFORE=$(git -C "$MIRROR" rev-parse HEAD)
# Hard reset rather than pull: the mirror is a read-only view of main, so local
# divergence (a stray edit, an interrupted fetch) must never block the sync.
if ! git -C "$MIRROR" fetch --quiet origin main; then
  echo "  fetch FAILED (offline? ssh key?) -- keeping existing content"
  exit 1
fi
git -C "$MIRROR" reset --quiet --hard origin/main || { echo "  reset FAILED"; exit 1; }
# reset --hard не трогает неотслеживаемое; без clean случайный каталог под
# catalog/ был бы слинкован в ~/.claude/skills навсегда. -x нужен потому, что
# корневой .gitignore прячет имена вроде __pycache__/ и packer_cache/, а
# вложенный git-репозиторий под catalog/ git удаляет только при двойном -f.
git -C "$MIRROR" clean -qxffd -- platform-gitops/platform-skills/catalog
AFTER=$(git -C "$MIRROR" rev-parse HEAD)
[ "$BEFORE" = "$AFTER" ] && echo "  catalog unchanged at ${AFTER:0:8}" \
                         || echo "  catalog ${BEFORE:0:8} -> ${AFTER:0:8}"

mkdir -p "$SKILLS" || { echo "  не удалось создать $SKILLS -- выхожу"; exit 1; }

# Adopt every catalog skill. Only ever touch symlinks -- a real directory in
# ~/.claude/skills is a hand-made local skill and is left strictly alone.
for src in "$CATALOG"/*/; do
  name=$(basename "$src")
  dst="$SKILLS/$name"
  if [ -L "$dst" ]; then
    [ "$(readlink "$dst")" = "${src%/}" ] || { ln -sfn "${src%/}" "$dst"; echo "  repointed $name"; }
  elif [ -e "$dst" ]; then
    echo "  SKIP $name -- real directory, not a symlink (local skill?)"
  else
    ln -s "${src%/}" "$dst"; echo "  linked $name (new)"
  fi
done

# Управляемые симлинки, которых больше нет в каталоге. Цель может быть ЖИВА --
# например ссылка в старый рабочий чекаут на скилл, удалённый из main, -- поэтому
# проверки на висячесть недостаточно. Признак "наш": цель лежит в каком-либо
# platform-skills/catalog/, чем личные ссылки пользователя не являются.
for dst in "$SKILLS"/*; do
  [ -L "$dst" ] || continue
  name=$(basename "$dst")
  [ -d "$CATALOG/$name" ] && continue
  case "$(readlink "$dst")" in
    */platform-skills/catalog/*) rm "$dst"; echo "  removed $name (no longer in catalog)" ;;
  esac
done

# Drop symlinks whose target is gone (skill deprecated/renamed upstream).
for dst in "$SKILLS"/*; do
  [ -L "$dst" ] || continue
  [ -e "$dst" ] && continue
  # Только наши: чужой симлинк на временно недоступную цель -- не наш мусор.
  case "$(readlink "$dst")" in
    "$CATALOG"/*) rm "$dst"; echo "  removed $(basename "$dst") (dangling)" ;;
    *) echo "  KEEP $(basename "$dst") -- dangling but not ours" ;;
  esac
done

# /tmp/review-watch.sh is generated from the skill body and caches across
# sessions; a catalog change makes it stale, and its freshness predicate only
# gets consulted when the skill is invoked. Drop it so it is regenerated.
if [ "$(cat "$STATE" 2>/dev/null)" != "$AFTER" ]; then
  if [ -f /tmp/review-watch.sh ]; then
    if rm -f /tmp/review-watch.sh 2>/dev/null; then
      echo "  dropped stale /tmp/review-watch.sh"
    else
      # /tmp -- 1777: файл может принадлежать другому пользователю, и тогда
      # удалить его нельзя никогда. Состояние не фиксируем (повторим на
      # следующем тике), но и прогон не роняем: симлинки уже сведены.
      echo "  ВНИМАНИЕ: /tmp/review-watch.sh не удаляется (чужой владелец?) -- кеш остаётся протухшим"
      echo "[$(date -u +%FT%TZ)] sync done"
      exit 0
    fi
  fi
  # Пишем состояние ТОЛЬКО после успешной инвалидации, поэтому прерванный
  # прогон приводит к повтору на следующем тике, а не к молчаливому пропуску.
  echo "$AFTER" > "$STATE"
fi

echo "[$(date -u +%FT%TZ)] sync done"
