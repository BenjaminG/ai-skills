// The hooks environment carries `import.meta.url` (its ESM loader); the lib
// the hooks tsconfig names does not know it. What the loader seats a module
// with, and the only way to reach the plugin's own files at run time.
interface ImportMeta {
  url: string
}
