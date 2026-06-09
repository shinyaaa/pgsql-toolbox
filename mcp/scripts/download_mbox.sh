#!/usr/bin/env bash
set -euo pipefail

# Download PostgreSQL mailing list archives in mbox format.
# Usage: ./scripts/download_mbox.sh LIST_NAME START_YYYYMM END_YYYYMM [output_dir]
# Example: ./scripts/download_mbox.sh pgsql-hackers 202401 202601
#          ./scripts/download_mbox.sh pgsql-general 202401 202601
#
# Behaviour:
#   - The current month AND the previous month are always re-downloaded, even
#     when the caller's START is later. Messages keep arriving in a month for a
#     while after it ends (moderation, late replies), so freezing a month the
#     instant the calendar rolls over silently drops those late messages.
#   - Downloads are atomic: data is written to a ".partial" file, validated as a
#     real mbox, and only then moved into place. A failed or truncated transfer
#     therefore never overwrites a known-good file, and is retried automatically.
#   - Any download/validation failure makes the script exit non-zero so callers
#     (cron, systemd, the ingester wrapper) can detect a bad run instead of
#     ingesting a partial archive as if it were complete.

LIST="${1:?Usage: $0 LIST_NAME START_YYYYMM END_YYYYMM [output_dir]}"
START="${2:?Usage: $0 LIST_NAME START_YYYYMM END_YYYYMM [output_dir]}"
END="${3:?Usage: $0 LIST_NAME START_YYYYMM END_YYYYMM [output_dir]}"
OUTDIR="${4:-./data/mbox}/${LIST}"

mkdir -p "$OUTDIR"

BASE_URL="https://www.postgresql.org/list/${LIST}/mbox"

# prev_month YYYYMM -> the preceding YYYYMM
prev_month() {
    local y="${1:0:4}" m="${1:4:2}"
    if [[ "$m" == "01" ]]; then
        printf '%04d12' $(( y - 1 ))
    else
        printf '%04d%02d' "$y" $(( 10#$m - 1 ))
    fi
}

# Months >= REFRESH_FROM are always re-downloaded; older existing months are
# treated as immutable and skipped. REFRESH_FROM is the month before END.
REFRESH_FROM="$(prev_month "$END")"

# Always cover the refresh window even if the caller asked for a later START.
if [[ "$START" -gt "$REFRESH_FROM" ]]; then
    START="$REFRESH_FROM"
fi

failed=0

# Show a progress bar only on an interactive terminal; stay quiet (but still
# report errors via -S) when output is redirected to a log file.
if [[ -t 2 ]]; then
    progress=(--progress-bar)
else
    progress=(--no-progress-meter)
fi

current="$START"
while [[ "$current" -le "$END" ]]; do
    year="${current:0:4}"
    month="${current:4:2}"
    filename="${LIST}.${current}"
    outpath="${OUTDIR}/${filename}"

    if [[ -f "$outpath" && "$current" -lt "$REFRESH_FROM" ]]; then
        echo "SKIP: ${filename} (immutable past month, already present)"
    else
        url="${BASE_URL}/${filename}"
        tmp="${outpath}.partial"
        echo "DOWNLOADING: ${url}"
        if curl -fSL "${progress[@]}" --retry 3 --retry-delay 5 --retry-all-errors \
                -u archives:antispam -o "$tmp" "$url"; then
            # A valid mbox begins with a "From " separator line. Reject anything
            # else (empty body, HTML error page, truncated transfer).
            if [[ -s "$tmp" ]] && head -n 1 "$tmp" | grep -q "^From "; then
                mv -f "$tmp" "$outpath"
                echo "OK: ${filename} ($(du -h "$outpath" | cut -f1))"
            else
                echo "ERROR: ${filename} is not a valid mbox; keeping previous file" >&2
                rm -f "$tmp"
                failed=1
            fi
        else
            echo "ERROR: failed to download ${filename}; keeping previous file" >&2
            rm -f "$tmp"
            failed=1
        fi
    fi

    # Increment month
    if [[ "$month" == "12" ]]; then
        year=$(( year + 1 ))
        month="01"
    else
        month=$(printf "%02d" $(( 10#$month + 1 )))
    fi
    current="${year}${month}"
done

echo "Done. Files in ${OUTDIR}:"
ls -lh "$OUTDIR"/${LIST}.* 2>/dev/null || echo "(none)"

if [[ "$failed" -ne 0 ]]; then
    echo "Completed with errors — at least one month failed to download." >&2
    exit 1
fi
