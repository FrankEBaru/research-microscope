# Se carga con `source`. Deja en FIX_DIR el directorio con manifest.json.
# Orden: RRM_OFFLINE_DIR, RRM_OFFLINE_TAR, RRM_OFFLINE_SYNTH=1,
# offline-fixtures/ si ya es la versión y la rama pedidas, y si no, los
# archivos de datos/offline/ en la rama claude/rrm-50-plan-b1 de
# FrankEBaru/research-microscope-compass (gh api, sin crear Releases).
# RRM_OFFLINE_VERSION elige v2 (default) o v3. RRM_OFFLINE_BRANCH cambia la rama.

COMPASS_REPO="${RRM_OFFLINE_REPO:-FrankEBaru/research-microscope-compass}"
COMPASS_BRANCH="${RRM_OFFLINE_BRANCH:-claude/rrm-50-plan-b1}"

offline_version() {
  local raw="${RRM_OFFLINE_VERSION:-v2}"
  raw="$(printf '%s' "$raw" | tr '[:upper:]' '[:lower:]')"
  raw="${raw#offline-fixtures-}"
  raw="${raw#v}"
  if [[ ! "$raw" =~ ^[0-9]+$ ]]; then
    echo "RRM_OFFLINE_VERSION debe ser v2, v3 (o 2, 3)." >&2
    return 1
  fi
  printf 'v%s\n' "$raw"
}

_install_archive() {
  local root="$1" dest="$2" tar_path="$3" stamp="$4"
  local parts=()
  if [[ -f "$tar_path" ]]; then
    parts=("$tar_path")
  else
    local f
    for f in "${tar_path}"*part-*; do
      [[ -f "$f" ]] && parts+=("$f")
    done
    if [[ "${#parts[@]}" == 0 && "$tar_path" == *part-* ]]; then
      for f in "${tar_path}"*; do
        [[ -f "$f" ]] && parts+=("$f")
      done
    fi
  fi
  if [[ "${#parts[@]}" == 0 ]]; then
    echo "El archivo no es un .tar.gz ni partes *.part-aa, *.part-ab…: ${tar_path}" >&2
    return 1
  fi
  local tmp src=""
  tmp="$(mktemp -d "$root/offline-fixtures.tmp.XXXXXX")"
  if ! cat "${parts[@]}" | tar -xzf - -C "$tmp"; then
    rm -rf "$tmp"
    echo "No pude descomprimir ${tar_path}." >&2
    return 1
  fi
  if [[ -f "$tmp/manifest.json" ]]; then
    src="$tmp"
  elif [[ -f "$tmp/offline-fixtures/manifest.json" ]]; then
    src="$tmp/offline-fixtures"
  else
    local sub
    for sub in "$tmp"/*/; do
      if [[ -f "${sub}manifest.json" ]]; then
        src="${sub%/}"
        break
      fi
    done
  fi
  if [[ -z "$src" ]]; then
    rm -rf "$tmp"
    echo "El archivo no trae manifest.json." >&2
    return 1
  fi
  rm -rf "$dest"
  mv "$src" "$dest"
  rm -rf "$tmp"
  printf '%s' "$stamp" >"$dest/.rrm-tar-stamp"
  FIX_DIR="$dest"
}

_require_gh() {
  local ver="$1"
  if ! command -v gh >/dev/null 2>&1; then
    echo "Falta gh para bajar ${ver} de ${COMPASS_REPO} (datos/offline/, rama ${COMPASS_BRANCH})." >&2
    echo "Instala gh y corre: gh auth login" >&2
    echo "O usa una carpeta local: RRM_OFFLINE_DIR=/ruta (con manifest.json)." >&2
    return 1
  fi
  if ! gh auth status >/dev/null 2>&1; then
    echo "gh no está autenticado. Corre: gh auth login" >&2
    echo "Sin eso no puedo bajar ${ver} desde ${COMPASS_REPO} (rama ${COMPASS_BRANCH})." >&2
    echo "O usa RRM_OFFLINE_DIR=/ruta con manifest.json." >&2
    return 1
  fi
}

_stamp_matches() {
  local dest="$1"
  local stamp="branch=${COMPASS_BRANCH} version=${2} sha256="
  [[ -f "$dest/manifest.json" && -f "$dest/.rrm-release" ]] && [[ "$(cat "$dest/.rrm-release")" == "$stamp"* ]]
}

# Checkout de compass al lado del repo, o la ruta de Frank. No cambia de rama.
_compass_candidates() {
  local root="$1" dir
  if [[ -n "${RRM_OFFLINE_COMPASS:-}" ]]; then
    printf '%s\n' "$RRM_OFFLINE_COMPASS"
  fi
  for dir in "$root/../research-microscope-compass" "${HOME:-}/projects/hackaton/research-microscope-compass"; do
    if [[ -d "$dir" ]]; then
      (cd "$dir" && pwd)
    fi
  done
}

_tree_has_version() {
  local dir="$1" ver="$2" hit=""
  [[ -d "$dir/datos/offline" ]] || return 1
  hit="$(find "$dir/datos/offline" -type f -name "*fixtures-${ver}*" -print -quit 2>/dev/null || true)"
  [[ -n "$hit" ]]
}

# Imprime el directorio raíz (el que contiene datos/offline). Si es un extracto
# temporal, la segunda línea es ese temporal para borrarlo después.
_materialize_compass() {
  local dir="$1" ver="$2" ref="" tmp
  if _tree_has_version "$dir" "$ver"; then
    printf '%s\n' "$dir"
    return 0
  fi
  if [[ ! -d "$dir/.git" && ! -f "$dir/.git" ]]; then
    return 1
  fi
  if git -C "$dir" rev-parse --verify --quiet "refs/remotes/origin/${COMPASS_BRANCH}" >/dev/null; then
    ref="origin/${COMPASS_BRANCH}"
  elif git -C "$dir" rev-parse --verify --quiet "${COMPASS_BRANCH}" >/dev/null; then
    ref="${COMPASS_BRANCH}"
  else
    return 1
  fi
  tmp="$(mktemp -d)"
  if ! git -C "$dir" archive "$ref" datos/offline | tar -x -C "$tmp"; then
    rm -rf "$tmp"
    return 1
  fi
  if ! _tree_has_version "$tmp" "$ver"; then
    rm -rf "$tmp"
    return 1
  fi
  printf '%s\n%s\n' "$tmp" "$tmp"
}

_fetch_local() {
  local root="$1" dest="$2" ver="$3" dir tree cleanup rc
  [[ "${RRM_OFFLINE_NO_LOCAL:-}" == "1" ]] && return 1
  while IFS= read -r dir; do
    [[ -n "$dir" ]] || continue
    cleanup=""
    tree="$(_materialize_compass "$dir" "$ver")" || continue
    cleanup="$(printf '%s\n' "$tree" | sed -n '2p')"
    tree="$(printf '%s\n' "$tree" | sed -n '1p')"
    if python3 "$root/scripts/fetch_offline_fixtures.py" \
      --from-dir "$tree" \
      --branch "$COMPASS_BRANCH" \
      --version "$ver" \
      --dest "$dest" \
      --cache "$root/offline-fixtures.cache"; then
      rc=0
    else
      rc=1
    fi
    [[ -n "$cleanup" ]] && rm -rf "$cleanup"
    if [[ "$rc" == 0 ]]; then
      echo "Fixtures ${ver} leídos del checkout local: ${dir}"
      FIX_DIR="$dest"
      return 0
    fi
    if [[ -n "${RRM_OFFLINE_COMPASS:-}" && "$dir" == "$RRM_OFFLINE_COMPASS" ]]; then
      return 1
    fi
  done < <(_compass_candidates "$root" | awk '!seen[$0]++')
  return 1
}

_fetch_branch() {
  local root="$1" dest="$2" ver="$3"
  if _stamp_matches "$dest" "$ver"; then
    FIX_DIR="$dest"
    return 0
  fi
  if _fetch_local "$root" "$dest" "$ver"; then
    return 0
  fi
  _require_gh "$ver" || return 1
  python3 "$root/scripts/fetch_offline_fixtures.py" \
    --repo "$COMPASS_REPO" \
    --branch "$COMPASS_BRANCH" \
    --version "$ver" \
    --dest "$dest" \
    --cache "$root/offline-fixtures.cache" || return 1
  FIX_DIR="$dest"
}

resolve_fixtures() {
  local root="$1"
  local dest="$root/offline-fixtures"
  local synth="${RRM_OFFLINE_SYNTH_DIR:-$root/offline-fixtures-synth}"
  FIX_DIR=""
  FIX_SYNTH=0

  if [[ -n "${RRM_OFFLINE_DIR:-}" ]]; then
    if [[ ! -f "$RRM_OFFLINE_DIR/manifest.json" ]]; then
      echo "RRM_OFFLINE_DIR no tiene manifest.json." >&2
      return 1
    fi
    FIX_DIR="$RRM_OFFLINE_DIR"
    return 0
  fi

  if [[ -n "${RRM_OFFLINE_TAR:-}" ]]; then
    local tar_path="$RRM_OFFLINE_TAR" parts=() f stamp=""
    if [[ -f "$tar_path" ]]; then
      parts=("$tar_path")
    else
      for f in "${tar_path}"*part-*; do
        [[ -f "$f" ]] && parts+=("$f")
      done
      if [[ "${#parts[@]}" == 0 && "$tar_path" == *part-* ]]; then
        for f in "${tar_path}"*; do
          [[ -f "$f" ]] && parts+=("$f")
        done
      fi
    fi
    if [[ "${#parts[@]}" == 0 ]]; then
      echo "RRM_OFFLINE_TAR no apunta a un .tar.gz ni a sus partes *.part-aa, *.part-ab…" >&2
      return 1
    fi
    stamp="$(ls -l --time-style=+%s "${parts[@]}" | awk '{print $5 ":" $6}' | tr '\n' ' ')"
    if [[ -f "$dest/manifest.json" && -f "$dest/.rrm-tar-stamp" && "$(cat "$dest/.rrm-tar-stamp")" == "$stamp" ]]; then
      FIX_DIR="$dest"
      return 0
    fi
    _install_archive "$root" "$dest" "$tar_path" "$stamp" || return 1
    return 0
  fi

  if [[ "${RRM_OFFLINE_SYNTH:-}" == "1" ]]; then
    if ! python3 "$root/scripts/build_ui_fixtures.py" --out "$synth" >/dev/null; then
      echo "No pude generar los fixtures sintéticos." >&2
      return 1
    fi
    echo "Fixtures sintéticos (texto de prueba, no son papers reales): ${synth}"
    FIX_DIR="$synth"
    FIX_SYNTH=1
    return 0
  fi

  local ver
  ver="$(offline_version)" || return 1
  _fetch_branch "$root" "$dest" "$ver" || return 1
}
