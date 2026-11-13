// Bundled SVG icons are imported as text (esbuild --loader:.svg=text).
declare module "*.svg" {
  const content: string;
  export default content;
}
