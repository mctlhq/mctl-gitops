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
# Опции ДОПИСЫВАЕМ к тому, что уже задано, а не подставляем вместо. Форма
# ${VAR:-...} сохраняла чужое значение целиком: launchd-профиль с
# GIT_SSH_COMMAND="ssh -i ~/.ssh/work" оставлял fetch без BatchMode и без
# таймаутов, то есть ровно с тем поведением, которое здесь запрещено.
export GIT_SSH_COMMAND="${GIT_SSH_COMMAND:-ssh} -o BatchMode=yes -o ConnectTimeout=15 -o ServerAliveInterval=15 -o ServerAliveCountMax=3"

REMOTE="git@github.com:mctlhq/mctl-gitops.git"
MIRROR="$HOME/.claude/skills-catalog"
SPARSE_PATH="platform-gitops/platform-skills/catalog"
CATALOG="$MIRROR/$SPARSE_PATH"
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
  # TZ=UTC обязателен: ps печатает время старта в текущей зоне процесса.
  # Ноутбук переезжает через часовые пояса; смена зоны между записью и
  # сверкой превратила бы тот же момент старта в другую строку, живой
  # держатель был бы объявлен "переиспользованным pid" и лок увели бы у него.
  st=$(TZ=UTC ps -p "$1" -o lstart= 2>/dev/null) || return 1
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
# inode каталога: BSD и GNU stat несовместимы, поэтому пробуем оба.
dir_inode() { stat -f %i "$1" 2>/dev/null || stat -c %i "$1" 2>/dev/null || true; }
if ! mkdir "$LOCK" 2>/dev/null; then
  # mkdir падает не только из-за занятости: нет ~/.claude, каталог только для
  # чтения, кончилось место. Без этой проверки такой отказ уходил бы в ветку
  # конкуренции -- pid и inode пустые, возраст 0 -- и каждый тик рапортовал бы
  # "синк уже идёт" с кодом 0, вечно и молча.
  if [ ! -d "$LOCK" ]; then
    echo "[$(date -u +%FT%TZ)] не удалось создать $LOCK, и его там нет -- отказ окружения (права? место? нет ~/.claude?)"
    exit 1
  fi
  # Запоминаем, КАКОЙ каталог осматриваем: к моменту перехвата на этом месте
  # может оказаться уже другой.
  LOCK_INO=$(dir_inode "$LOCK")
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
    # атомарно, но САМО ПО СЕБЕ недостаточно: если второй прогон задержался, а
    # первый успел перехватить, пересоздать лок и уйти в работу, то mv второго
    # унесёт уже НОВЫЙ, живой каталог -- оба окажутся в одном git-репозитории.
    # Поэтому переносим только то, что осматривали: сверяем inode до переноса и
    # содержимое после, а чужой каталог возвращаем на место.
    echo "[$(date -u +%FT%TZ)] снимаю осиротевший лок ($STALE)"
    TAKEN="$LOCK.stale.$$"
    if [ -n "$LOCK_INO" ] && [ "$(dir_inode "$LOCK")" != "$LOCK_INO" ]; then
      echo "  лок уже пересоздан другим прогоном -- выхожу"; exit 0
    fi
    mv "$LOCK" "$TAKEN" 2>/dev/null || { echo "  перехват достался другому прогону -- выхожу"; exit 0; }
    if [ "$(cat "$TAKEN/pid" 2>/dev/null)" != "$RECORDED" ]; then
      # Между проверкой и mv каталог успели подменить: мы унесли живой лок.
      # Возвращаем и уходим -- работает тот, кто его создал.
      # Возврат делаем НЕ через mv: пока мы разбирались, путь мог занять третий
      # прогон, а mv в существующий каталог кладёт источник ВНУТРЬ него
      # ($LOCK/$TAKEN), и лок оказывается ни у кого. Сначала резервируем путь
      # собственным mkdir -- он атомарен и либо наш, либо чужой, -- и только
      # потом переносим содержимое внутрь уже удерживаемого каталога.
      if mkdir "$LOCK" 2>/dev/null; then
        cp -R "$TAKEN"/. "$LOCK"/ 2>/dev/null
        rm -rf "$TAKEN"
        echo "  унесли не тот лок, вернул содержимое на место -- выхожу"
      else
        rm -rf "$TAKEN"
        echo "  унесли не тот лок, а путь уже занят третьим прогоном -- выхожу"
      fi
      exit 0
    fi
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
   && [ "$(git -C "$MIRROR" config --get core.sparseCheckout 2>/dev/null)" = "true" ] \
   && git -C "$MIRROR" sparse-checkout list 2>/dev/null | grep -qxF "$SPARSE_PATH"; then
  MIRROR_OK=1
fi
# Клон, оборванный после создания .git, но до настройки remote/ref'ов, иначе
# считался бы валидным зеркалом вечно: fetch падал бы каждый раз, а само
# зеркало никогда не пересоздавалось.
# Мало того, что разреженность включена -- в наборе должен быть НАШ путь.
# `git sparse-checkout set scripts`, выполненный в этом зеркале руками, оставляет
# core.sparseCheckout=true, и предикат по одному флагу принял бы зеркало, в
# котором каталога скиллов нет вовсе. Тогда reset сохраняет чужую разреженность,
# цикл по catalog/ не находит ничего, а финальная уборка сносит ВСЕ управляемые
# симлинки как "исчезнувшие из каталога".
# core.sparseCheckout проверяется отдельно, потому что клон идёт с --no-checkout:
# прогон, оборванный между clone и sparse-checkout, оставляет .git, HEAD и
# origin в полном порядке -- три предиката выше проходят, -- но без разреженной
# конфигурации следующий reset --hard раскладывает всё дерево и подтягивает
# блобы всего репозитория вместо каталога скиллов.
MIRROR_RECREATED=0
if [ "$MIRROR_OK" = "0" ]; then
  MIRROR_RECREATED=1
  echo "  зеркало отсутствует или непригодно ($MIRROR) -- пересоздаю"
  # Собираем замену РЯДОМ и меняем местами только когда она готова. Снос до
  # клона означал бы, что при первом же оффлайне (или отвале ssh) все симлинки
  # в ~/.claude/skills повисают, и скиллы пропадают до возвращения сети --
  # ровно та недоступность, ради устранения которой всё это писалось.
  NEW_MIRROR="$MIRROR.new.$$"
  rm -rf "$NEW_MIRROR"
  if ! git clone --filter=blob:none --no-checkout --single-branch --branch main \
       "$REMOTE" "$NEW_MIRROR"; then
    rm -rf "$NEW_MIRROR"
    echo "  clone FAILED -- прежнее зеркало оставлено на месте"; exit 1
  fi
  if ! git -C "$NEW_MIRROR" sparse-checkout set --cone "$SPARSE_PATH"; then
    rm -rf "$NEW_MIRROR"
    echo "  sparse-checkout FAILED -- иначе checkout вытянул бы весь репозиторий"; exit 1
  fi
  if ! git -C "$NEW_MIRROR" checkout main; then
    rm -rf "$NEW_MIRROR"
    echo "  checkout FAILED -- прежнее зеркало оставлено на месте"; exit 1
  fi
  # Подмена: старое в сторону, новое на место, старое снести. Симлинки указывают
  # на путь, а не на inode, поэтому окно недоступности -- два системных вызова.
  OLD_MIRROR="$MIRROR.old.$$"
  rm -rf "$OLD_MIRROR"
  # -L обязателен рядом с -e: все файловые проверки, кроме -h/-L, идут ПО ссылке,
  # поэтому битый симлинк на месте зеркала (его цель удалили) даёт -e ложь. Тогда
  # старое имя не убирается, а следующий mv не может положить каталог поверх
  # не-каталога -- ENOTDIR, -- и каждый следующий прогон падает там же, зеркало
  # не восстанавливается никогда.
  if [ -e "$MIRROR" ] || [ -L "$MIRROR" ]; then
    mv "$MIRROR" "$OLD_MIRROR"
  fi
  if ! mv "$NEW_MIRROR" "$MIRROR"; then
    # -L и здесь: если зеркалом была битая ссылка, она и в $OLD_MIRROR битая,
    # -e снова ложь, возврат молча не происходит -- а лог при этом уверяет, что
    # прежнее возвращено.
    if [ -e "$OLD_MIRROR" ] || [ -L "$OLD_MIRROR" ]; then
      mv "$OLD_MIRROR" "$MIRROR"
    fi
    rm -rf "$NEW_MIRROR"
    echo "  подмена зеркала FAILED -- прежнее возвращено"; exit 1
  fi
  rm -rf "$OLD_MIRROR"
fi

BEFORE=$(git -C "$MIRROR" rev-parse HEAD)
# Отпечаток берём по РАБОЧЕМУ ДЕРЕВУ скилла, а не по коммиту: правку, сделанную
# в зеркале руками, reset --hard снесёт, но HEAD при этом не сдвинется -- и
# сравнение коммитов сочло бы, что ничего не изменилось, пока кеш watcher-а
# продолжает исполнять код, выведенный из уже снесённой версии.
watch_fingerprint() {
  find "$CATALOG/review-watch" -type f -exec shasum {} + 2>/dev/null \
    | sed "s|$MIRROR/||" | sort | shasum | cut -d" " -f1
}
WATCH_BEFORE=$(watch_fingerprint)
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
# Статус clean проверяем наравне с остальными git-командами: без set -e его
# отказ (снятое право на запись, immutable-флаг на файле) прошёл бы молча, и
# оставшийся мусор уехал бы в ~/.claude/skills как настоящий скилл, а прогон
# закончился бы бодрым "sync done".
if ! git -C "$MIRROR" clean -qxffd -- "$SPARSE_PATH"; then
  echo "  clean FAILED -- в каталоге остался неотслеживаемый мусор, не свожу ссылки"; exit 1
fi
AFTER=$(git -C "$MIRROR" rev-parse HEAD)
WATCH_AFTER=$(watch_fingerprint)
[ "$BEFORE" = "$AFTER" ] && echo "  catalog unchanged at ${AFTER:0:8}" \
                         || echo "  catalog ${BEFORE:0:8} -> ${AFTER:0:8}"

mkdir -p "$SKILLS" || { echo "  не удалось создать $SKILLS -- выхожу"; exit 1; }
# Без set -e "ln ...; echo ..." возвращает успех группы, и провалившийся симлинк
# уходил в лог как "repointed", а launchd записывал прогон удачным. Копим флаг и
# честно падаем в конце -- иначе протухшая ссылка живёт молча.
RECONCILE_FAILED=0

# Каталог общий для нескольких клиентов, и metadata.yaml перечисляет, какие из
# них скилл поддерживает. Часть скиллов (mctl-platform, argocd-health-remediation)
# заявляет только mcp/codex/openclaw и содержит инструкции вида "выполни codex
# mcp ...", бесполезные и сбивающие с толку в Claude Code. Линкуем только те,
# что заявили claude.
# Значение скалярного ключа верхнего уровня, нормализованное: без хвостового
# комментария и без обрамляющих кавычек. YAML тут разбирается ровно настолько,
# насколько нужно для плоского metadata.yaml из семи ключей, который CI и так
# валидирует через yaml.safe_load. Полноценный парсер означал бы зависимость от
# python3 с PyYAML, а скрипт ходит под launchd и должен обходиться базовой
# системой; блочные скаляры, якоря и вложенные структуры здесь не поддержаны
# намеренно.
meta_scalar() { # $1 = metadata.yaml, $2 = ключ
  awk -v k="$2" '
    index($0, k ":") == 1 {
      sub("^" k ":[[:space:]]*", "")
      sub(/[[:space:]]+#.*$/, "")
      sub(/[[:space:]]+$/, "")
      q = sprintf("%c", 39)
      if (length($0) >= 2 &&
          ((substr($0, 1, 1) == "\"" && substr($0, length($0), 1) == "\"") ||
           (substr($0, 1, 1) == q    && substr($0, length($0), 1) == q)))
        $0 = substr($0, 2, length($0) - 2)
      print; exit
    }' "$1"
}

# Элементы списка верхнего уровня -- и потокового ("[a, b]"), и блочного ("- a"),
# по одному на строку. Диапазон sed'а здесь не годится: он ВКЛЮЧАЕТ строку,
# оборвавшую диапазон, так что идущий следом "description: ... claude ..."
# попадал в выборку и засчитывался как рантайм. awk выходит ДО печати границы.
meta_list() { # $1 = metadata.yaml, $2 = ключ
  awk -v k="$2" '
    function strip(line) {
      # Комментарий -- и хвостовой, и занимающий всю строку. Без этого
      # "runtimes: [codex] # not for claude" давал токен claude и скилл
      # линковался бы вопреки декларации.
      sub(/[[:space:]]+#.*$/, "", line); sub(/^[[:space:]]*#.*$/, "", line)
      return line
    }
    index($0, k ":") == 1 { inb = 1; sub("^" k ":[[:space:]]*", ""); $0 = strip($0); if ($0 != "") print; next }
    inb && /^[[:space:]]*-/ { print strip($0); next }
    inb && /^[[:space:]]+[^[:space:]]/ { print strip($0); next }
    inb { exit }' "$1" \
  | tr -c 'A-Za-z0-9_-' '\n' | grep -v '^$'
}

# Есть ли ключ верхнего уровня вообще. Отсутствующий ключ и присутствующий, но
# пустой -- разные вещи, и meta_list их не различает: оба дают пусто.
meta_has_key() { # $1 = metadata.yaml, $2 = ключ
  awk -v k="$2" 'index($0, k ":") == 1 { found = 1; exit } END { exit !found }' "$1"
}

supports_claude() { # $1 = каталог скилла
  local m="$1/metadata.yaml" st rt
  # Нет metadata.yaml -- линкуем: отсутствие декларации не повод прятать скилл,
  # иначе новый скилл молча не доехал бы до сессии.
  [ -f "$m" ] || return 0
  # draft прячем: validate-platform-skills.py отказывается привязывать его к
  # тенантам и ролям, и рабочая станция не должна быть дырой в этом правиле.
  # deprecated, наоборот, оставляем: снятие с поддержки в этом репозитории --
  # шаг НЕразрушающий (валидатор допускает существующие привязки к deprecated, а
  # воркфлоу деприкейта продолжает отдавать содержимое, пока привязку не сняли
  # явно). Отзывать симлинк на ближайшем тике значило бы, что скилл исчезает у
  # работающего человека посреди сессии -- жёстче, чем поступает сама платформа.
  st=$(meta_scalar "$m" status)
  [ -z "$st" ] || [ "$st" = "active" ] || [ "$st" = "deprecated" ] || return 1
  rt=$(meta_list "$m" runtimes)
  if [ -z "$rt" ]; then
    # Секции нет вовсе -- тот же случай, что и отсутствующий файл: не прячем.
    # А вот `runtimes: []` -- это явное заявление "ни одного клиента", и
    # материализатор OpenClaw в этом репозитории понимает его именно так.
    # Валидатор пустой список пропускает, так что различать обязаны мы.
    meta_has_key "$m" runtimes && return 1
    return 0
  fi
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
        */platform-skills/catalog/*)
          if rm "$dst"; then echo "  removed $name (не поддерживает claude)"
          else echo "  rm FAILED для $name"; RECONCILE_FAILED=1; fi ;;
      esac
    fi
    continue
  fi
  if [ -L "$dst" ]; then
    if [ "$(readlink "$dst")" != "${src%/}" ]; then
      if ln -sfn "${src%/}" "$dst"; then echo "  repointed $name"
      else echo "  ln FAILED для $name"; RECONCILE_FAILED=1; fi
    fi
  elif [ -e "$dst" ]; then
    echo "  SKIP $name -- real directory, not a symlink (local skill?)"
  else
    if ln -s "${src%/}" "$dst"; then echo "  linked $name (new)"
    else echo "  ln FAILED для $name"; RECONCILE_FAILED=1; fi
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
    */platform-skills/catalog/*)
      if rm "$dst"; then echo "  removed $name (no longer in catalog)"
      else echo "  rm FAILED для $name"; RECONCILE_FAILED=1; fi ;;
  esac
done

# Drop symlinks whose target is gone (skill deprecated/renamed upstream).
for dst in "$SKILLS"/*; do
  [ -L "$dst" ] || continue
  [ -e "$dst" ] && continue
  # Только наши: чужой симлинк на временно недоступную цель -- не наш мусор.
  case "$(readlink "$dst")" in
    "$CATALOG"/*)
      if rm "$dst"; then echo "  removed $(basename "$dst") (dangling)"
      else echo "  rm FAILED для $(basename "$dst")"; RECONCILE_FAILED=1; fi ;;
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
# ...но НЕ вслепую на каждом тике. Bootstrap скилла пишет файл, затем chmod +x,
# затем nohup; удаление, попавшее в этот зазор, роняет запуск, и watcher не
# стартует вовсе. Довод про открытый inode защищает уже ЗАПУЩЕННЫЙ процесс и на
# эту последовательность не распространяется.
#
# Возраст файла отличить запуск не может: скилл переписывает кеш только когда его
# предикат по содержимому не сошёлся, поэтому при штатном запуске ГОДНОГО кеша
# mtime остаётся старым всё время между проверкой и nohup. Поэтому основной
# признак -- не возраст, а факт, что источник в каталоге действительно изменился:
# только тогда кеш мог протухнуть по нашей вине, и только тогда его надо снимать.
#
# Но одного факта изменения мало: если оно совпало с запуском watcher-а, отсрочка
# пропускает тик, а на следующем тике diff уже пуст -- и протухший кеш остался бы
# жить до следующего, ни с чем не связанного изменения review-watch, то есть
# ровно тот инцидент 2026-08-31, ради которого всё это писалось. Поэтому
# необходимость снять кеш ЗАПОМИНАЕТСЯ меткой и переживает тик: она ставится при
# изменении и снимается только когда файл действительно удалён (или его уже нет).
CACHE_PENDING="$HOME/.claude/skills-sync.cache-pending"
CACHE_GRACE=120
cache_age_seconds() {
  local m
  m=$(stat -f %m "$1" 2>/dev/null) || m=$(stat -c %Y "$1" 2>/dev/null) || m=""
  [ -n "$m" ] || { echo 0; return; }
  echo $(( $(date +%s) - m ))
}
WATCH_SKILL_CHANGED=0
if [ "$MIRROR_RECREATED" = "1" ]; then
  # Зеркало собрано заново -- сравнивать не с чем, считаем, что изменилось.
  WATCH_SKILL_CHANGED=1
elif [ "$WATCH_BEFORE" != "$WATCH_AFTER" ]; then
  WATCH_SKILL_CHANGED=1
fi
# Долг держим в переменной, а метку -- лишь как способ пережить тик. Читать
# обратно сам файл было бы неверно: неудавшаяся запись выглядела бы как
# "review-watch не менялся" -- ровно та потеря долга, ради которой метка и
# заведена, -- да ещё и с этой неправдой в логе.
CACHE_DUE=0
[ -f "$CACHE_PENDING" ] && CACHE_DUE=1
if [ "$WATCH_SKILL_CHANGED" = "1" ]; then
  CACHE_DUE=1
  if ! : > "$CACHE_PENDING"; then
    echo "  не удалось записать $CACHE_PENDING -- долг снять кеш не переживёт этот тик"
    RECONCILE_FAILED=1
  fi
fi
if [ ! -f /tmp/review-watch.sh ]; then
  # Снимать нечего -- долг закрыт.
  rm -f "$CACHE_PENDING"
elif [ "$CACHE_DUE" = "0" ]; then
  echo "  review-watch в каталоге не менялся -- кеш /tmp/review-watch.sh не трогаю"
elif [ "$(cache_age_seconds /tmp/review-watch.sh)" -le "$CACHE_GRACE" ]; then
  # Метку НЕ снимаем: вернёмся к этому на следующем тике.
  echo "  /tmp/review-watch.sh только что записан -- откладываю до следующего тика"
elif rm -f /tmp/review-watch.sh 2>/dev/null; then
  rm -f "$CACHE_PENDING"
  echo "  dropped cached /tmp/review-watch.sh (скилл обновился)"
else
  # /tmp -- 1777: файл может принадлежать другому пользователю, и тогда удалить
  # его нельзя никогда. Прогон не роняем: симлинки уже сведены.
  echo "  ВНИМАНИЕ: /tmp/review-watch.sh не удаляется (чужой владелец?) -- кеш остаётся протухшим"
fi
if [ "$RECONCILE_FAILED" = "1" ]; then
  echo "[$(date -u +%FT%TZ)] sync FAILED -- не все шаги прошли, подробности выше"
  exit 1
fi
echo "[$(date -u +%FT%TZ)] sync done"
