# Linear evidence — uploading screenshots and placing them in the summary

Autonomous runs capture one proof screenshot per scenario and extra debug shots on
failure (see SKILL.md Step 2). This doc covers how those PNGs reach Linear.

## Two paths, two mechanisms

| Use | Where it lands | Mechanism |
| -- | -- | -- |
| **Proof** (one per scenario) | a cell of the summary's Scenarios table | upload first → write the URL into the cell (see below) |
| **Debug** (failures) | end-gallery of the per-finding comment | `linear issue comment add … --attach shot.png` (repeatable) |

The split exists because `linear … --attach` always appends `![file](url)` at the
**end** of the comment — fine for a debug gallery, useless for a specific table cell.
To put an image in a cell you need its permanent `assetUrl` *before* composing the body.

## Upload helper

`scripts/upload-image.mjs` uploads one local image and prints its permanent Linear
asset URL to stdout — nothing else — so the caller can capture it:

```bash
URL=$(node scripts/upload-image.mjs ./qa-evidence-BOF-218/1.2.png) \
  || echo "upload failed — fall back to --attach gallery"
```

Auth: `LINEAR_API_TOKEN` if set, else `linear auth token`. Exits non-zero on any
failure (caller should degrade to a plain `--attach` gallery rather than abort).

### Raw recipe (what the helper does, for reference / debugging)

`linear api` exposes the same `fileUpload` mutation if you ever need it by hand:

```bash
linear api --variable ct=image/png --variable fn=shot.png --variable sz=12345 <<'GRAPHQL'
mutation($ct: String!, $fn: String!, $sz: Int!) {
  fileUpload(contentType: $ct, filename: $fn, size: $sz, makePublic: true) {
    success uploadFile { assetUrl uploadUrl headers { key value } }
  }
}
GRAPHQL
```

Then PUT the file bytes to `uploadUrl` with **every** returned header (plus
`Content-Type`); after a 2xx, `assetUrl` is the permanent URL.

## Proof cell: inline image vs. clickable link

Build the Scenarios table with a `Proof` column. Default to the **inline image** form:

```
| # | Cell | Result | Proof |
| -- | -- | -- | -- |
| §1.2 | MA, any date | ✅ 85% accepted | ![](<assetUrl>) |
```

**Render risk:** Linear's editor (ProseMirror) treats images as block-level nodes,
and table cells may only accept inline content — so a cell image can be dropped or
shown oversized. **First real run: open the posted summary comment in Linear.**
- Renders cleanly → keep `![](<assetUrl>)`.
- Dropped or oversized → switch every Proof cell to the **link form** (always renders):

```
| §1.2 | MA, any date | ✅ 85% accepted | [📷 §1.2](<assetUrl>) |
```

Once you know which form your workspace renders, stick with it for future runs.
