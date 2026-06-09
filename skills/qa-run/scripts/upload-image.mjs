#!/usr/bin/env node
// upload-image - upload a local image to Linear and print its permanent asset URL.
// Used by qa-run to place screenshots inside the summary table's Proof cell
// (the linear CLI's --attach only appends images at the end of a comment).
//
// Requires Node 22+ (built-in fetch). No npm dependencies.
//
// Usage:   node upload-image.mjs <file>
// Auth:    LINEAR_API_TOKEN env, else `linear auth token`.
// Output:  stdout = the permanent assetUrl (single line, nothing else).
//          stderr = progress / errors. Exit 0 on success, non-zero on failure.
// Caller:  URL=$(node upload-image.mjs shot.png) || fall back to `--attach`.

import { readFileSync, statSync } from "fs";
import { basename, extname } from "path";
import { execFileSync } from "child_process";

const API = "https://api.linear.app/graphql";
const MIME = {
  ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
  ".gif": "image/gif", ".webp": "image/webp",
};

const die = (msg) => { console.error(`upload-image: ${msg}`); process.exit(1); };

const file = process.argv[2];
if (!file) die("usage: upload-image.mjs <file>");

let size;
try { size = statSync(file).size; } catch { die(`cannot stat ${file}`); }
const filename = basename(file);
const contentType = MIME[extname(file).toLowerCase()] || "application/octet-stream";

let token = process.env.LINEAR_API_TOKEN;
if (!token) {
  try { token = execFileSync("linear", ["auth", "token"], { encoding: "utf8" }).trim(); }
  catch { die("no LINEAR_API_TOKEN and `linear auth token` failed"); }
}

const gql = async (query, variables) => {
  const res = await fetch(API, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: token },
    body: JSON.stringify({ query, variables }),
  });
  const json = await res.json();
  if (json.errors) die(`GraphQL: ${JSON.stringify(json.errors)}`);
  return json.data;
};

// 1. Request a signed upload URL.
const { fileUpload } = await gql(
  `mutation($ct: String!, $fn: String!, $sz: Int!) {
     fileUpload(contentType: $ct, filename: $fn, size: $sz, makePublic: true) {
       success uploadFile { assetUrl uploadUrl headers { key value } }
     }
   }`,
  { ct: contentType, fn: filename, sz: size }
);
if (!fileUpload?.success || !fileUpload.uploadFile) die("fileUpload was not granted");
const { assetUrl, uploadUrl, headers } = fileUpload.uploadFile;

// 2. PUT the raw bytes to the signed URL with every header Linear returned.
const putHeaders = { "Content-Type": contentType };
for (const { key, value } of headers) putHeaders[key] = value;
const put = await fetch(uploadUrl, { method: "PUT", headers: putHeaders, body: readFileSync(file) });
if (!put.ok) die(`PUT failed: ${put.status} ${put.statusText}`);

// 3. The asset URL is now permanent.
process.stdout.write(assetUrl + "\n");
