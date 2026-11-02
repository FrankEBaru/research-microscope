# Se carga con `source`. Deja en FIX_DIR el directorio con manifest.json.
# Orden: RRM_OFFLINE_DIR, RRM_OFFLINE_TAR, RRM_OFFLINE_SYNTH=1, offline-fixtures/,
# y si no hay nada, los fixtures sintéticos. No usa red ni gh.

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
    local tar_path="$RRM_OFFLINE_TAR" parts=() stamp=""
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
      echo "RRM_OFFLINE_TAR no apunta a un .tar.gz ni a sus partes *.part-aa, *.part-ab…" >&2
      return 1
    fi
    stamp="$(ls -l --time-style=+%s "${parts[@]}" | awk '{print $5 ":" $6}' | tr '\n' ' ')"
    if [[ -f "$dest/manifest.json" && -f "$dest/.rrm-tar-stamp" && "$(cat "$dest/.rrm-tar-stamp")" == "$stamp" ]]; then
      FIX_DIR="$dest"
      return 0
    fi
    local tmp
    tmp="$(mktemp -d "$root/offline-fixtures.tmp.XXXXXX")"
    if ! cat "${parts[@]}" | tar -xzf - -C "$tmp"; then
      rm -rf "$tmp"
      echo "No pude descomprimir RRM_OFFLINE_TAR." >&2
      return 1
    fi
    local src=""
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
      echo "RRM_OFFLINE_TAR no trae manifest.json." >&2
      return 1
    fi
    rm -rf "$dest"
    mv "$src" "$dest"
    rm -rf "$tmp"
    printf '%s' "$stamp" >"$dest/.rrm-tar-stamp"
    FIX_DIR="$dest"
    return 0
  fi

  if [[ "${RRM_OFFLINE_SYNTH:-}" != "1" && -f "$dest/manifest.json" ]]; then
    FIX_DIR="$dest"
    return 0
  fi

  if ! python3 "$root/scripts/build_ui_fixtures.py" --out "$synth" >/dev/null; then
    echo "No pude generar los fixtures sintéticos." >&2
    return 1
  fi
  echo "Fixtures sintéticos (texto de prueba, no son papers reales): ${synth}"
  FIX_DIR="$synth"
  FIX_SYNTH=1
}
