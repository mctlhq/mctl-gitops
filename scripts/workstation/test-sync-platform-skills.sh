#!/bin/bash
# Tests for sync-platform-skills.sh.
#
# Почему они существуют: логика скрипта (перехват стухшего лока, проверка
# пригодности разреженного зеркала, сведение симлинков, инвалидация кеша)
# набралась за девять раундов ревью, и в каждой из этих областей находили баг,
# причём несколько -- регрессии, внесённые при исправлении предыдущей находки.
# Проверялось всё вручную во временных песочницах, которые тут же выбрасывались.
# Это -- те же проверки, но committed. См. mctl-gitops#961.
#
# Сеть и ssh не нужны: фикстурный remote -- локальный bare-репозиторий, а
# git@github.com:... переписывается на него через url.insteadOf в поддельном
# HOME. Заодно это покрывает требование, что переписанный URL НЕ считается
# чужим origin и не заставляет пересоздавать зеркало.
#
#   ./scripts/workstation/test-sync-platform-skills.sh          # все тесты
#   ./scripts/workstation/test-sync-platform-skills.sh lock_    # по подстроке
set -uo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
SUT="$SCRIPT_DIR/sync-platform-skills.sh"
FILTER="${1:-}"

[ -f "$SUT" ] || { echo "не найден $SUT"; exit 1; }

PASSED=0
FAILED=0
FAILED_NAMES=()
CURRENT=""
CURRENT_FAILED=0

# Каждый тест живёт в собственном каталоге; здесь копятся все, чтобы прибрать их
# одним махом в конце (и не потерять при падении посреди теста).
ROOTS=()
KEEP_ROOTS=()
cleanup() {
  local r k keep
  for r in ${ROOTS+"${ROOTS[@]}"}; do
    keep=0
    for k in ${KEEP_ROOTS+"${KEEP_ROOTS[@]}"}; do
      [ "$r" = "$k" ] && keep=1
    done
    [ "$keep" = "1" ] && continue
    [ -n "$r" ] && [ -d "$r" ] && rm -rf "$r"
  done
}
trap cleanup EXIT

fail() { # $1 = сообщение
  echo "    ✗ $1"
  CURRENT_FAILED=1
}

assert_log() { # $1 = подстрока, $2 = пояснение
  if ! grep -qF -- "$1" "$LOG"; then
    fail "${2:-в логе нет} '$1'"
  fi
}

assert_no_log() { # $1 = подстрока
  if grep -qF -- "$1" "$LOG"; then
    fail "${2:-в логе НЕ должно быть} '$1'"
  fi
}

assert_link_to() { # $1 = имя скилла, $2 = ожидаемая цель
  local p="$SKILLS/$1"
  if [ ! -L "$p" ]; then fail "$1 -- не симлинк (или его нет)"; return; fi
  local got; got=$(readlink "$p")
  [ "$got" = "$2" ] || fail "$1 указывает на $got, ожидалось $2"
}

assert_linked() { # $1 = имя скилла из каталога
  assert_link_to "$1" "$CATALOG/$1"
}

assert_absent() { # $1 = имя
  local p="$SKILLS/$1"
  { [ -e "$p" ] || [ -L "$p" ]; } && fail "$1 не должен существовать в $SKILLS"
  return 0
}

assert_is_dir() { # $1 = имя
  local p="$SKILLS/$1"
  [ -d "$p" ] && [ ! -L "$p" ] || fail "$1 должен остаться настоящим каталогом"
}

assert_exit() { # $1 = ожидаемый код
  RC_ASSERTED=1
  [ "$RC" = "$1" ] || fail "код возврата $RC, ожидался $1"
}

# Прогон дошёл до конца И действительно свёл ссылки. Нужно всякий раз, когда
# тест утверждает, что чего-то НЕТ: отсутствие -- это ещё и то, что видно после
# прогона, упавшего на клоне, и без этой проверки такой тест зеленел бы, ни разу
# не дойдя до проверяемой логики.
assert_synced() {
  assert_exit 0
  assert_log "sync done"
  assert_linked alpha
}

assert_file() { # $1 = путь
  [ -f "$1" ] || fail "нет файла $1"
}

assert_no_file() { # $1 = путь
  [ -e "$1" ] && fail "файл $1 не должен существовать"
  return 0
}

# ---------------------------------------------------------------- фикстура

# Скилл в фикстурном каталоге. $1 = имя, $2 = содержимое metadata.yaml
# (пустое -- файла не будет вовсе).
seed_skill() {
  local name="$1" meta="${2-}"
  mkdir -p "$SEED/platform-gitops/platform-skills/catalog/$name"
  printf '# %s\n\nтело скилла\n' "$name" \
    > "$SEED/platform-gitops/platform-skills/catalog/$name/SKILL.md"
  [ -n "$meta" ] && printf '%s\n' "$meta" \
    > "$SEED/platform-gitops/platform-skills/catalog/$name/metadata.yaml"
  return 0
}

seed_commit() { # $1 = сообщение
  git -C "$SEED" add -A
  git -C "$SEED" -c user.name=t -c user.email=t@t commit -qm "$1"
  git -C "$SEED" push -q origin main
}

setup() { # $1 = имя теста
  CURRENT="$1"
  CURRENT_FAILED=0
  RC_ASSERTED=0
  ROOT=$(mktemp -d "${TMPDIR:-/tmp}/skills-sync-test.XXXXXX")
  ROOTS+=("$ROOT")
  REMOTE_DIR="$ROOT/remote.git"
  HOME_DIR="$ROOT/home"
  MIRROR="$HOME_DIR/.claude/skills-catalog"
  CATALOG="$MIRROR/platform-gitops/platform-skills/catalog"
  SKILLS="$HOME_DIR/.claude/skills"
  LOG="$HOME_DIR/.claude/skills-sync.log"
  LOCK="$HOME_DIR/.claude/skills-sync.lock"
  CACHE="$HOME_DIR/.claude/tmp/review-watch.sh"
  CACHE_PENDING="$HOME_DIR/.claude/skills-sync.cache-pending"
  SEED="$ROOT/seed"

  mkdir -p "$HOME_DIR/.claude"
  git init -q --bare "$REMOTE_DIR"
  # blobless-клон по file:// требует явного разрешения фильтров на стороне
  # отдающего; без него git clone --filter молча отдал бы всё дерево.
  git -C "$REMOTE_DIR" config uploadpack.allowFilter true
  git init -q -b main "$SEED"
  git -C "$SEED" remote add origin "$REMOTE_DIR"

  seed_skill review-watch 'name: review-watch
status: active
runtimes: [claude]'
  seed_skill alpha 'name: alpha
status: active
runtimes: [claude, codex]'
  seed_skill beta 'name: beta
status: active
runtimes: [codex]'
  seed_skill gamma 'name: gamma
status: draft
runtimes: [claude]'
  seed_skill delta ''      # без metadata.yaml -- линкуется по умолчанию
  seed_commit "seed"

  # Тот самый url.insteadOf: origin в зеркале останется буквальным
  # git@github.com:mctlhq/mctl-gitops.git, что и сверяет предикат пригодности.
  cat > "$HOME_DIR/.gitconfig" <<EOF
[url "file://$REMOTE_DIR"]
	insteadOf = git@github.com:mctlhq/mctl-gitops.git
[user]
	name = test
	email = test@example.invalid
[protocol "file"]
	allow = always
EOF
}

# Прогон скрипта в поддельном HOME. env -i: наследованные GIT_*, SSH_* и прочее
# из сессии не должны влиять на результат.
run_sync() {
  env -i \
    HOME="$HOME_DIR" \
    PATH="$PATH" \
    bash "$SUT"
  RC=$?
}

finish() {
  # Тест, не проверивший код возврата, легко зеленеет вхолостую: почти все
  # утверждения здесь -- об ОТСУТСТВИИ чего-либо (симлинка нет, файла нет), а
  # это верно и для прогона, упавшего на клоне, и для прогона, оборвавшегося
  # посреди пересоздания зеркала. Ревью нашло три таких теста в трёх раундах
  # подряд, поэтому требование вынесено в сам харнесс, а не в дисциплину автора.
  if [ "$RC_ASSERTED" = "0" ]; then
    fail "тест не проверил код возврата (assert_exit / assert_synced)"
  fi
  if [ "$CURRENT_FAILED" = "0" ]; then
    PASSED=$((PASSED + 1))
    echo "  ✓ $CURRENT"
  else
    FAILED=$((FAILED + 1))
    FAILED_NAMES+=("$CURRENT")
    # Песочницу упавшего теста НЕ убираем: без лога и разложенных файлов
    # разбирать нечего.
    KEEP_ROOTS+=("$ROOT")
    echo "  ✗ $CURRENT  (песочница: $ROOT, лог: $LOG)"
  fi
}

# Пропускать ли тест по фильтру из аргумента.
skip() { # $1 = имя
  [ -z "$FILTER" ] && return 1
  case "$1" in *"$FILTER"*) return 1 ;; *) return 0 ;; esac
}

# Тот же разбор stat(1), что и в самом скрипте, и по той же причине: перебор
# "stat -f ... || stat -c ..." в ОДНОЙ подстановке склеивает вывод обеих попыток.
# GNU считает `-f` запросом про файловую систему, а `%i` -- именем файла: он
# печатает многострочный блок (со счётчиком свободных блоков, который меняется
# от записи к записи) И возвращает 1, так что запасной вызов дописывает к этому
# блоку настоящий inode. Сравнение "до/после" тогда сравнивает не inode'ы, а
# блоки, и на Linux расходится просто оттого, что между замерами что-то писали.
# Ровно этот баг PR чинит в production-скрипте -- воспроизвести его в тесте,
# который должен его ловить, было бы смешно.
if stat -c %i . >/dev/null 2>&1; then
  inode_of() { stat -c %i "$1" 2>/dev/null; }
else
  inode_of() { stat -f %i "$1" 2>/dev/null; }
fi

# Заведомо свободный pid: перебираем, пока kill -0 не перестанет его находить.
dead_pid() {
  local p
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    p=$(( 30000 + RANDOM % 5000 ))
    kill -0 "$p" 2>/dev/null || { echo "$p"; return 0; }
  done
  echo ""   # не нашли -- тест сам это заметит
}

# ---------------------------------------------------------------- тесты

test_bootstrap_links_catalog_skills() {
  setup bootstrap_links_catalog_skills
  run_sync
  assert_exit 0
  assert_log "sync done"
  assert_linked review-watch
  assert_linked alpha
  assert_linked delta
  finish
}

# Фильтр по metadata.yaml: не-claude рантайм и draft не линкуются.
test_bootstrap_filters_by_metadata() {
  setup bootstrap_filters_by_metadata
  run_sync
  assert_synced           # иначе «не слинкован» верно и для упавшего прогона
  assert_absent beta
  assert_absent gamma
  finish
}

# `runtimes: []` -- явное «ни одного клиента», в отличие от отсутствующей секции.
test_empty_runtimes_list_is_not_claude() {
  setup empty_runtimes_list_is_not_claude
  seed_skill epsilon 'name: epsilon
status: active
runtimes: []'
  seed_commit "epsilon"
  run_sync
  assert_synced
  assert_absent epsilon
  finish
}

# Хвостовой комментарий не должен давать токен claude.
test_runtimes_trailing_comment_ignored() {
  setup runtimes_trailing_comment_ignored
  seed_skill zeta 'name: zeta
status: active
runtimes: [codex] # not for claude'
  seed_commit "zeta"
  run_sync
  assert_synced
  assert_absent zeta
  finish
}

test_second_run_reuses_mirror() {
  setup second_run_reuses_mirror
  run_sync
  local ino_before; ino_before=$(inode_of "$MIRROR/.git")
  [ -n "$ino_before" ] || fail "не удалось прочитать inode зеркала"
  : > "$LOG"
  run_sync
  assert_exit 0
  assert_no_log "пересоздаю" "зеркало пересоздано на втором прогоне"
  assert_log "catalog unchanged"
  local ino_after; ino_after=$(inode_of "$MIRROR/.git")
  [ "$ino_before" = "$ino_after" ] || fail "каталог .git подменён без пересоздания"
  finish
}

# Оборванный клон: .git, HEAD и origin на месте, разреженности нет. Без
# отдельной проверки core.sparseCheckout зеркало считалось бы годным, а
# следующий reset --hard раскладывал бы всё дерево репозитория.
test_mirror_without_sparse_config_recreated() {
  setup mirror_without_sparse_config_recreated
  run_sync
  git -C "$MIRROR" sparse-checkout disable >/dev/null 2>&1
  : > "$LOG"
  run_sync
  assert_exit 0
  assert_log "пересоздаю"
  assert_linked alpha
  finish
}

# Регрессия: `git sparse-checkout set` на ЧУЖОЙ путь оставляет
# core.sparseCheckout=true, и предикат по одному флагу принял бы зеркало без
# каталога скиллов. Тогда цикл не находит ничего, а уборка сносит ВСЕ
# управляемые симлинки как «исчезнувшие из каталога».
test_mirror_with_foreign_sparse_path_recreated() {
  setup mirror_with_foreign_sparse_path_recreated
  run_sync
  git -C "$MIRROR" sparse-checkout set --cone scripts >/dev/null 2>&1
  : > "$LOG"
  run_sync
  assert_exit 0
  assert_log "пересоздаю"
  assert_linked alpha
  assert_linked review-watch
  finish
}

test_foreign_origin_recreated() {
  setup foreign_origin_recreated
  run_sync
  git -C "$MIRROR" remote set-url origin "https://example.invalid/other.git"
  : > "$LOG"
  run_sync
  # Без assert_synced тест зеленел бы и при обрыве пересоздания: старое зеркало
  # осталось бы на месте, ссылка на alpha -- годной, а "пересоздаю" уже в логе.
  assert_synced
  assert_log "пересоздаю"
  finish
}

test_removed_skill_is_unlinked() {
  setup removed_skill_is_unlinked
  run_sync
  assert_linked alpha
  rm -rf "$SEED/platform-gitops/platform-skills/catalog/alpha"
  seed_commit "drop alpha"
  : > "$LOG"
  run_sync
  assert_exit 0
  assert_absent alpha
  assert_log "alpha (no longer in catalog)"
  assert_linked review-watch
  finish
}

# Ради чего второй цикл вообще существует: ссылка на скилл, которого больше нет
# в каталоге, но цель ЖИВА -- например в старом рабочем чекауте. Проверки на
# висячесть тут недостаточно, такую ссылку снимает только признак «наша».
test_stale_link_into_other_checkout_removed() {
  setup stale_link_into_other_checkout_removed
  local other="$ROOT/old-checkout/platform-gitops/platform-skills/catalog/legacy"
  mkdir -p "$other"
  echo "# legacy" > "$other/SKILL.md"
  mkdir -p "$SKILLS"
  ln -s "$other" "$SKILLS/legacy"
  run_sync
  assert_exit 0
  assert_absent legacy
  assert_log "legacy (no longer in catalog)"
  [ -d "$other" ] || fail "снесена сама цель, а не ссылка"
  finish
}

# Скилл, переставший заявлять claude, тоже должен отвязываться.
test_skill_dropping_claude_is_unlinked() {
  setup skill_dropping_claude_is_unlinked
  run_sync
  assert_linked alpha
  seed_skill alpha 'name: alpha
status: active
runtimes: [codex]'
  seed_commit "alpha: drop claude"
  : > "$LOG"
  run_sync
  assert_exit 0
  assert_log "sync done"
  assert_absent alpha
  assert_log "не поддерживает claude"
  finish
}

# Имя намеренно совпадает с каталожным скиллом: иначе ветка «это настоящий
# каталог, не трогаем» просто не исполняется. При отсутствии проверки ln -s
# положил бы симлинк ВНУТРЬ каталога, а сам каталог остался бы каталогом --
# проверка одного лишь -d ничего бы не поймала.
test_local_real_directory_preserved() {
  setup local_real_directory_preserved
  mkdir -p "$SKILLS/alpha"
  echo "мой скилл" > "$SKILLS/alpha/SKILL.md"
  run_sync
  assert_exit 0
  assert_is_dir alpha
  assert_file "$SKILLS/alpha/SKILL.md"
  assert_log "SKIP alpha"
  assert_no_file "$SKILLS/alpha/alpha"
  finish
}

# Симлинк пользователя на несуществующую цель -- не наш мусор: цель могла быть
# временно недоступна (внешний диск), и снос был бы потерей данных.
test_foreign_dangling_symlink_preserved() {
  setup foreign_dangling_symlink_preserved
  mkdir -p "$SKILLS"
  ln -s "$ROOT/nowhere/some-skill" "$SKILLS/foreign"
  run_sync
  assert_synced
  [ -L "$SKILLS/foreign" ] || fail "чужой висячий симлинк снесён"
  assert_log "KEEP foreign"
  finish
}

# А вот наш собственный висячий (цель внутри зеркала исчезла) -- снимается.
test_own_dangling_symlink_removed() {
  setup own_dangling_symlink_removed
  run_sync
  mkdir -p "$SKILLS"
  ln -s "$CATALOG/vanished" "$SKILLS/vanished"
  : > "$LOG"
  run_sync
  assert_synced
  assert_absent vanished
  assert_log "removed vanished"
  finish
}

# --------------------------------------------------------------- лок

test_lock_held_by_live_process_respected() {
  setup lock_held_by_live_process_respected
  mkdir -p "$LOCK"
  # Личность держателя -- ровно то, что пишет сам скрипт: pid и время старта.
  printf '%s %s' "$$" "$(TZ=UTC ps -p $$ -o lstart=)" > "$LOCK/pid"
  run_sync
  assert_exit 0
  assert_log "синк уже идёт"
  assert_no_log "sync start" "прогон не должен был начаться"
  [ -d "$LOCK" ] || fail "чужой лок снесён"
  finish
}

test_lock_with_dead_pid_reclaimed() {
  setup lock_with_dead_pid_reclaimed
  local dead; dead=$(dead_pid)
  [ -n "$dead" ] || { fail "не нашёл свободный pid"; finish; return; }
  mkdir -p "$LOCK"
  printf '%s %s' "$dead" "Mon Jan  1 00:00:00 2001" > "$LOCK/pid"
  run_sync
  assert_exit 0
  assert_log "снимаю осиротевший лок"
  assert_log "мёртв"
  assert_log "sync done"
  finish
}

# pid переиспользован: номер занят, но другим процессом. kill -0 тут врёт, и без
# сверки времени старта лок залипал бы навсегда.
test_lock_with_reused_pid_reclaimed() {
  setup lock_with_reused_pid_reclaimed
  mkdir -p "$LOCK"
  printf '%s %s' "$$" "Mon Jan  1 00:00:00 2001" > "$LOCK/pid"
  run_sync
  assert_exit 0
  assert_log "переиспользован"
  assert_log "sync done"
  finish
}

# Свежий лок без pid-файла -- это другой прогон между mkdir и записью pid.
test_lock_without_pid_fresh_respected() {
  setup lock_without_pid_fresh_respected
  mkdir -p "$LOCK"
  run_sync
  assert_exit 0
  assert_log "синк уже идёт"
  finish
}

# Тот же лок, но старше минуты: держателя убили в этом окне, иначе он вечен.
test_lock_without_pid_old_reclaimed() {
  setup lock_without_pid_old_reclaimed
  mkdir -p "$LOCK"
  touch -t 200001010000 "$LOCK"
  run_sync
  assert_exit 0
  assert_log "без живого pid и старше минуты"
  assert_log "sync done"
  finish
}

# Лок держится на время прогона и снимается по выходу, а метка владельца пишется.
test_lock_released_after_run() {
  setup lock_released_after_run
  run_sync
  assert_exit 0
  [ -d "$LOCK" ] && fail "лок остался после успешного прогона"
  finish
}

# ------------------------------------------------------- инвалидация кеша

# Кеш снимается, когда review-watch в каталоге изменился, и только тогда.
test_cache_dropped_when_watch_skill_changes() {
  setup cache_dropped_when_watch_skill_changes
  run_sync
  mkdir -p "$(dirname "$CACHE")"
  echo "старый кеш" > "$CACHE"
  touch -t 200001010000 "$CACHE"
  printf 'новое тело\n' \
    > "$SEED/platform-gitops/platform-skills/catalog/review-watch/SKILL.md"
  seed_commit "review-watch: update"
  : > "$LOG"
  run_sync
  assert_exit 0
  assert_log "dropped cached"
  assert_no_file "$CACHE"
  assert_no_file "$CACHE_PENDING"
  finish
}

test_cache_kept_when_watch_skill_unchanged() {
  setup cache_kept_when_watch_skill_unchanged
  run_sync
  mkdir -p "$(dirname "$CACHE")"
  echo "кеш" > "$CACHE"
  touch -t 200001010000 "$CACHE"
  printf 'не review-watch\n' \
    > "$SEED/platform-gitops/platform-skills/catalog/alpha/SKILL.md"
  seed_commit "alpha: update"
  : > "$LOG"
  run_sync
  assert_exit 0
  assert_log "не менялся"
  assert_file "$CACHE"
  finish
}

# Только что записанный кеш не трогаем: bootstrap скилла пишет файл, потом
# chmod +x, потом nohup -- удаление в этом зазоре срывает запуск watcher-а.
test_cache_deferred_when_just_written() {
  setup cache_deferred_when_just_written
  run_sync
  mkdir -p "$(dirname "$CACHE")"
  echo "только что" > "$CACHE"
  printf 'новое тело\n' \
    > "$SEED/platform-gitops/platform-skills/catalog/review-watch/SKILL.md"
  seed_commit "review-watch: update"
  : > "$LOG"
  run_sync
  assert_exit 0
  assert_log "откладываю до следующего тика"
  assert_file "$CACHE"
  assert_file "$CACHE_PENDING"   # долг обязан пережить тик
  finish
}

# Та самая регрессия 17-го раунда: отсрочка не должна ТЕРЯТЬ долг. На следующем
# тике каталог уже не меняется, и без метки протухший кеш жил бы до следующего,
# ни с чем не связанного изменения review-watch.
test_cache_debt_survives_to_next_tick() {
  setup cache_debt_survives_to_next_tick
  run_sync
  mkdir -p "$(dirname "$CACHE")"
  echo "только что" > "$CACHE"
  printf 'новое тело\n' \
    > "$SEED/platform-gitops/platform-skills/catalog/review-watch/SKILL.md"
  seed_commit "review-watch: update"
  run_sync                       # тик 1: отсрочка, метка поставлена
  assert_file "$CACHE_PENDING"
  touch -t 200001010000 "$CACHE" # кеш «состарился», каталог больше не меняется
  : > "$LOG"
  run_sync                       # тик 2: долг обязан сработать
  assert_synced
  assert_log "dropped cached"
  assert_no_file "$CACHE"
  assert_no_file "$CACHE_PENDING"
  finish
}

# Метку снимаем только когда файла действительно не стало.
test_cache_pending_cleared_when_cache_absent() {
  setup cache_pending_cleared_when_cache_absent
  run_sync
  : > "$CACHE_PENDING"
  : > "$LOG"
  run_sync
  assert_synced
  assert_no_file "$CACHE_PENDING"
  finish
}

# ------------------------------------------------------------- отказы

# Неотслеживаемый каталог под catalog/ не должен уезжать в ~/.claude/skills как
# настоящий скилл: reset --hard его не трогает, поэтому есть отдельный clean.
test_untracked_directory_in_catalog_cleaned() {
  setup untracked_directory_in_catalog_cleaned
  run_sync
  mkdir -p "$CATALOG/garbage"
  echo x > "$CATALOG/garbage/SKILL.md"
  : > "$LOG"
  run_sync
  assert_exit 0
  assert_absent garbage
  [ -d "$CATALOG/garbage" ] && fail "мусор остался в каталоге зеркала"
  finish
}

# Правка в зеркале руками откатывается, и это считается изменением скилла:
# сравнение одних лишь коммитов сочло бы, что ничего не произошло.
test_hand_edit_in_mirror_counts_as_change() {
  setup hand_edit_in_mirror_counts_as_change
  run_sync
  mkdir -p "$(dirname "$CACHE")"
  echo "кеш" > "$CACHE"
  touch -t 200001010000 "$CACHE"
  echo "правка руками" >> "$CATALOG/review-watch/SKILL.md"
  : > "$LOG"
  run_sync
  assert_synced
  assert_log "dropped cached"
  assert_no_file "$CACHE"
  finish
}

# Недоступный remote не должен ронять уже разложенные симлинки: зеркало
# остаётся прежним, скиллы продолжают работать.
test_fetch_failure_keeps_existing_links() {
  setup fetch_failure_keeps_existing_links
  run_sync
  assert_linked alpha
  rm -rf "$REMOTE_DIR"
  : > "$LOG"
  run_sync
  assert_exit 1
  assert_log "fetch FAILED"
  assert_linked alpha
  [ -d "$LOCK" ] && fail "лок не снят после аварийного выхода"
  finish
}

# Клон невозможен, а зеркала ещё нет -- падаем, но не оставляем огрызков.
test_clone_failure_leaves_no_partial_mirror() {
  setup clone_failure_leaves_no_partial_mirror
  rm -rf "$REMOTE_DIR"
  run_sync
  assert_exit 1
  assert_log "clone FAILED"
  # Прогон обязан остановиться ровно здесь: без этого он спотыкается о каждый
  # следующий шаг и заполняет лог вторичными отказами, из которых уже не видно,
  # что произошло на самом деле.
  assert_no_log "sparse-checkout FAILED" "после провала клона прогон продолжился"
  assert_no_log "fetch FAILED" "после провала клона прогон продолжился"
  [ -e "$MIRROR" ] && fail "после провального клона осталось зеркало"
  compgen -G "$HOME_DIR/.claude/skills-catalog.new.*" >/dev/null \
    && fail "остался незавершённый $MIRROR.new.*"
  finish
}

# ---------------------------------------------------------------- прогон

echo "sync-platform-skills.sh — тесты"
for t in $(declare -F | awk '{print $3}' | grep '^test_' | sort); do
  name=${t#test_}
  skip "$name" && continue
  "$t"
done

echo
# Фильтр, не совпавший ни с одним тестом, -- это опечатка, а не успех. Без этой
# проверки прогон печатал "OK: 0 тестов" и возвращал 0, то есть в CI такой вызов
# прошёл бы зелёным, ничего не проверив.
if [ -n "$FILTER" ] && [ "$((PASSED + FAILED))" = "0" ]; then
  echo "фильтр '$FILTER' не совпал ни с одним тестом"
  exit 2
fi
if [ "$FAILED" = "0" ]; then
  echo "OK: $PASSED тестов"
  exit 0
fi
echo "ПРОВАЛЕНО: $FAILED из $((PASSED + FAILED))"
for n in "${FAILED_NAMES[@]}"; do echo "  - $n"; done
exit 1
