#!/usr/bin/env bash
set -euo pipefail

# Download PostgreSQL mailing list archives in mbox format.
# Usage: ./scripts/download_mbox.sh LIST_NAME START_YYYYMM END_YYYYMM [output_dir]
# Example: ./scripts/download_mbox.sh pgsql-hackers 202401 202601
#          ./scripts/download_mbox.sh pgsql-general 202401 202601

LIST="${1:?Usage: $0 LIST_NAME START_YYYYMM END_YYYYMM [output_dir]}"
START="${2:?Usage: $0 LIST_NAME START_YYYYMM END_YYYYMM [output_dir]}"
END="${3:?Usage: $0 LIST_NAME START_YYYYMM END_YYYYMM [output_dir]}"
OUTDIR="${4:-./data/mbox}/${LIST}"

mkdir -p "$OUTDIR"

BASE_URL="https://www.postgresql.org/list/${LIST}/mbox"

current="$START"
while [[ "$current" -le "$END" ]]; do
    year="${current:0:4}"
    month="${current:4:2}"
    filename="${LIST}.${current}"
    outpath="${OUTDIR}/${filename}"

    if [[ -f "$outpath" ]]; then
        echo "SKIP: ${filename} (already exists)"
    else
        url="${BASE_URL}/${filename}"
        echo "DOWNLOADING: ${url}"
        curl -fSL -u archives:antispam -o "$outpath" "$url" || echo "WARN: Failed to download ${filename}"
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
