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

exec >>"$LOG" 2>&1

# launchd запускает нас каждые 15 мин, а README предлагает и ручной запуск.
# Два одновременных прогона дерутся за один git-репозиторий (index.lock), а в
# худшем случае один делает rm -rf зеркала, пока другой в нём checkout'ится.
# mkdir атомарен; flock(1) на macOS нет.
LOCK="$HOME/.claude/skills-sync.lock"
# Потолок удержания используется ТОЛЬКО когда личность держателя установить не
# удалось (см. holder_id ниже). Выселять по одному лишь возрасту нельзя: если
# ноутбук проспал час посреди синка, часы уходят вперёд, а держатель жив и
# продолжит работу после пробуждения.
LOCK_MAX_AGE=3600
# Личность процесса, а не только его номер: pid плюс время старта. kill -0
# доказывает, что номер занят, но не что занят нами -- после SIGKILL или паники
# ОС переиспользует номер под чужой долгоживущий процесс. Время старта их
# различает, и, в отличие от возраста лока, не врёт после сна машины.
holder_id() {
  local st
  st=$(ps -p "$1" -o lstart= 2>/dev/null) || return 1
  [ -n "$st" ] || return 1
  printf '%s %s' "$1" "$st"
}
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
  # В файле лежит "<pid> <время старта>" -- ровно то, что вернул holder_id.
  RECORDED=$(cat "$LOCK/pid" 2>/dev/null)
  HELD=${RECORDED%% *}
  AGE=$(lock_age_seconds)
  if [ -n "$HELD" ] && kill -0 "$HELD" 2>/dev/null; then
    CURRENT=$(holder_id "$HELD") || CURRENT=""
    if [ -n "$CURRENT" ] && [ "$CURRENT" != "$RECORDED" ]; then
      # Номер занят, но другим процессом: держателя убили, а pid переиспользован.
      # Без этой ветки kill -0 врал бы вечно и синк молча не шёл бы никогда.
      STALE="pid $HELD переиспользован (запуск не совпадает с записанным)"
    elif [ -z "$CURRENT" ] && [ "$AGE" -gt "$LOCK_MAX_AGE" ]; then
      # ps ничего не сказал -- личность не проверить. Только здесь возраст
      # остаётся последним доводом.
      STALE="удерживается ${AGE}s (> ${LOCK_MAX_AGE}s), личность держателя не проверить"
    fi
    # Личность совпала -- держатель honest-to-god жив, и никакой возраст его не
    # выселяет: проспавший час ноутбук не повод отнимать лок у работающего.
  elif [ -n "$HELD" ]; then
    STALE="pid $HELD мёртв"
  elif [ "$AGE" -gt 60 ]; then
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
# pid тоже под noclobber. Уснуть можно и МЕЖДУ двумя записями: тогда наш owner
# уже лежит, перехватчик снёс каталог и создал свой, и слепая запись pid
# подменила бы его запись -- оба прогона считали бы лок своим и полезли бы в
# один git-репозиторий.
if ! holder_id "$$" > "$LOCK/pid" 2>/dev/null; then
  set +C; echo "  лок перехвачен между записями -- выхожу"; exit 0
fi
set +C
# Перехватчик мог успеть создать каталог заново уже после нашей записи owner,
# и тогда обе записи выше легли в чужой лок. Владелец -- последнее слово.
if [ "$(cat "$LOCK/owner" 2>/dev/null)" != "$OWNER" ]; then
  echo "  лок перехвачен, владелец сменился -- выхожу"; exit 0
fi
trap '[ "$(cat "$LOCK/owner" 2>/dev/null)" = "$OWNER" ] && rm -rf "$LOCK"' EXIT

echo "[$(date -u +%FT%TZ)] sync start"

MIRROR_OK=0
if [ -d "$MIRROR/.git" ] \
   && git -C "$MIRROR" rev-parse --verify --quiet HEAD >/dev/null 2>&1 \
   && [ "$(git -C "$MIRROR" config --get remote.origin.url 2>/dev/null)" = "$REMOTE" ] \
   && [ "$(git -C "$MIRROR" config --get core.sparseCheckout 2>/dev/null)" = "true" ]; then
  MIRROR_OK=1
fi
# Клон, оборванный после создания .git, но до настройки remote/ref'ов, иначе
# считался бы валидным зеркалом вечно: fetch падал бы каждый раз, а само
# зеркало никогда не пересоздавалось.
# core.sparseCheckout проверяется отдельно, потому что клон идёт с --no-checkout:
# прогон, оборванный между clone и sparse-checkout, оставляет .git, HEAD и
# origin в полном порядке -- три предиката выше проходят, -- но без разреженной
# конфигурации следующий reset --hard раскладывает всё дерево и подтягивает
# блобы всего репозитория вместо каталога скиллов.
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
# Явный refspec, а не "origin main": обновление origin/main при сокращённой
# форме опирается на настроенный remote.origin.fetch. Если он потерян или
# изменён, fetch всё равно возвращает 0, но трогает только FETCH_HEAD -- и
# следующий reset --hard origin/main бесконечно возвращает старый коммит, молча
# и без единой ошибки в логе.
if ! git -C "$MIRROR" fetch --quiet origin +refs/heads/main:refs/remotes/origin/main; then
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

# Каталог общий для нескольких клиентов, и metadata.yaml перечисляет, какие из
# них скилл поддерживает. Часть скиллов (mctl-platform, argocd-health-remediation)
# заявляет только mcp/codex/openclaw и содержит инструкции вида "выполни codex
# mcp ...", бесполезные и сбивающие с толку в Claude Code. Линкуем только те,
# что заявили claude.
# Значение скалярного ключа верхнего уровня.
meta_scalar() { # $1 = metadata.yaml, $2 = ключ
  awk -v k="$2" '
    index($0, k ":") == 1 {
      sub("^" k ":[[:space:]]*", ""); sub(/[[:space:]]+$/, ""); print; exit
    }' "$1"
}

# Элементы списка верхнего уровня -- и потокового ("[a, b]"), и блочного ("- a"),
# по одному на строку. Диапазон sed'а здесь не годится: он ВКЛЮЧАЕТ строку,
# оборвавшую диапазон, так что идущий следом "description: ... claude ..."
# попадал в выборку и засчитывался как рантайм. awk выходит ДО печати границы.
meta_list() { # $1 = metadata.yaml, $2 = ключ
  awk -v k="$2" '
    index($0, k ":") == 1 { inb = 1; sub("^" k ":[[:space:]]*", ""); if ($0 != "") print; next }
    inb && /^[[:space:]]*-/ { print; next }
    inb && /^[[:space:]]+[^[:space:]]/ { print; next }
    inb { exit }' "$1" \
  | tr -c 'A-Za-z0-9_-' '\n' | grep -v '^$'
}

supports_claude() { # $1 = каталог скилла
  local m="$1/metadata.yaml" st rt
  # Нет metadata.yaml -- линкуем: отсутствие декларации не повод прятать скилл,
  # иначе новый скилл молча не доехал бы до сессии.
  [ -f "$m" ] || return 0
  # Пригодным платформа считает только active: validate-platform-skills.py
  # отказывается привязывать draft и deprecated к тенантам и ролям, и рабочая
  # станция не должна быть дырой в этом правиле.
  st=$(meta_scalar "$m" status)
  [ -z "$st" ] || [ "$st" = "active" ] || return 1
  rt=$(meta_list "$m" runtimes)
  # Секции нет вовсе -- тот же случай, что и отсутствующий файл: не прячем.
  [ -n "$rt" ] || return 0
  # Сравнение с целым токеном, а не поиск подстроки: "[mcp, claude]" даёт токен
  # claude (скобка -- разделитель), а "claude-next" остаётся одним токеном и не
  # засчитывается.
  printf '%s\n' "$rt" | grep -qx claude
}

# Adopt every catalog skill. Only ever touch symlinks -- a real directory in
# ~/.claude/skills is a hand-made local skill and is left strictly alone.
for src in "$CATALOG"/*/; do
  name=$(basename "$src")
  dst="$SKILLS/$name"
  if ! supports_claude "${src%/}"; then
    # Ссылка могла быть создана раньше, до фильтра или до правки metadata.yaml.
    if [ -L "$dst" ]; then
      case "$(readlink "$dst")" in
        */platform-skills/catalog/*) rm "$dst"; echo "  removed $name (не поддерживает claude)" ;;
      esac
    fi
    continue
  fi
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
# Удаляем БЕЗУСЛОВНО, а не только при смене коммита. Сессия, загрузившая старый
# скилл до синка, может пересоздать старый кеш уже ПОСЛЕ него; при сверке с
# сохранённым состоянием каждый следующий тик видел бы "коммит не менялся" и
# пропускал инвалидацию, а протухший watcher жил бы до следующего коммита в
# каталог. Удаление дешёвое: скилл пишет файл заново при первом же обращении, а
# уже запущенный watcher держит открытый inode и снятия ссылки не замечает.
if [ -f /tmp/review-watch.sh ]; then
  if rm -f /tmp/review-watch.sh 2>/dev/null; then
    echo "  dropped cached /tmp/review-watch.sh"
  else
    # /tmp -- 1777: файл может принадлежать другому пользователю, и тогда
    # удалить его нельзя никогда. Прогон не роняем: симлинки уже сведены.
    echo "  ВНИМАНИЕ: /tmp/review-watch.sh не удаляется (чужой владелец?) -- кеш остаётся протухшим"
  fi
fi
echo "[$(date -u +%FT%TZ)] sync done"
