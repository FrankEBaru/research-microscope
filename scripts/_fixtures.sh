# Se carga con `source`. Deja en FIX_DIR el directorio con manifest.json.
# Orden: RRM_OFFLINE_DIR, RRM_OFFLINE_TAR, RRM_OFFLINE_SYNTH=1,
# offline-fixtures/ si ya es el release pedido, y si no, gh release download
# desde FrankEBaru/research-microscope-compass (datos/offline/, Releases
# offline-fixtures-v2 y offline-fixtures-v3). RRM_OFFLINE_VERSION elige la
# versión (default v2; v3 con RRM_OFFLINE_VERSION=v3).

COMPASS_REPO="${RRM_OFFLINE_REPO:-FrankEBaru/research-microscope-compass}"

offline_release_tag() {
  local raw="${RRM_OFFLINE_VERSION:-v2}"
  raw="$(printf '%s' "$raw" | tr '[:upper:]' '[:lower:]')"
  raw="${raw#offline-fixtures-}"
  raw="${raw#v}"
  if [[ ! "$raw" =~ ^[0-9]+$ ]]; then
    echo "RRM_OFFLINE_VERSION debe ser v2, v3 (o 2, 3)." >&2
    return 1
  fi
  printf 'offline-fixtures-v%s\n' "$raw"
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

_fetch_release() {
  local root="$1" dest="$2" tag="$3"
  if ! command -v gh >/dev/null 2>&1; then
    echo "Falta gh para bajar ${tag} de ${COMPASS_REPO} (datos/offline/)." >&2
    echo "Instala gh y corre: gh auth login" >&2
    echo "O usa una carpeta local: RRM_OFFLINE_DIR=/ruta (con manifest.json)." >&2
    return 1
  fi
  if ! gh auth status >/dev/null 2>&1; then
    echo "gh no está autenticado. Corre: gh auth login" >&2
    echo "Sin eso no puedo bajar ${tag} desde ${COMPASS_REPO}." >&2
    echo "O usa RRM_OFFLINE_DIR=/ruta con manifest.json." >&2
    return 1
  fi
  local tmp
  tmp="$(mktemp -d "$root/offline-fixtures.gh.XXXXXX")"
  if ! gh release download "$tag" --repo "$COMPASS_REPO" --pattern "${tag}.tar.gz" --clobber --dir "$tmp"; then
    rm -rf "$tmp"
    echo "gh no pudo bajar ${tag}.tar.gz de ${COMPASS_REPO}." >&2
    return 1
  fi
  if ! _install_archive "$root" "$dest" "$tmp/${tag}.tar.gz" "release:${tag}"; then
    rm -rf "$tmp"
    return 1
  fi
  rm -rf "$tmp"
  printf '%s' "$tag" >"$dest/.rrm-release"
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

  local tag
  tag="$(offline_release_tag)" || return 1
  if [[ -f "$dest/manifest.json" && -f "$dest/.rrm-release" && "$(cat "$dest/.rrm-release")" == "$tag" ]]; then
    FIX_DIR="$dest"
    return 0
  fi

  _fetch_release "$root" "$dest" "$tag" || return 1
}
