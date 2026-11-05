// Invented sample records. Later slices replace these with the repository API.

export type Grouping = "category" | "type" | "directory";

export interface PackageRecord {
  name: string;
  displayName: string;
  version: string;
  category: string;
  type: "exe" | "msi" | "msix" | "nupkg" | "ps1";
  directory: string;
  description: string;
  testing: boolean;
  production: boolean;
  minimumOs: string;
  architectures: string;
  executable: string;
  installPath: string;
}

export const EDITABLE_FIELDS = ["displayName", "description", "testing", "production"] as const;
export type EditableField = (typeof EDITABLE_FIELDS)[number];

function record(
  name: string,
  version: string,
  category: string,
  type: PackageRecord["type"],
  directory: string,
  description: string,
  production: boolean,
  minimumOs: string,
  architectures: string,
  executable: string,
  installPath: string,
): PackageRecord {
  return {
    name,
    displayName: name,
    version,
    category,
    type,
    directory,
    description,
    testing: true,
    production,
    minimumOs,
    architectures,
    executable,
    installPath,
  };
}

export const SAMPLE_PACKAGES: readonly PackageRecord[] = [
  record("Firefox", "136.0", "Browsers", "exe", "apps/browsers", "A fast, independent web browser.", true, "10.0.19045", "x64, arm64", "firefox.exe", "%ProgramFiles%\\Mozilla Firefox\\firefox.exe"),
  record("Chrome", "134.0.6998.89", "Browsers", "msi", "apps/browsers", "A browser built by Google.", false, "10.0.19045", "x64, arm64", "chrome.exe", "%ProgramFiles%\\Google\\Chrome\\Application\\chrome.exe"),
  record("Blender", "4.3.2", "Creative", "msi", "apps/creative", "Tools for 3D creation and animation.", false, "10.0.19045", "x64", "blender.exe", "%ProgramFiles%\\Blender Foundation\\Blender 4.3\\blender.exe"),
  record("Inkscape", "1.4", "Creative", "msi", "apps/creative", "A vector graphics editor.", true, "10.0.19045", "x64", "inkscape.exe", "%ProgramFiles%\\Inkscape\\bin\\inkscape.exe"),
  record("VLC", "3.0.21", "Media", "exe", "apps/media", "An open source media player.", true, "10.0.17763", "x64, arm64", "vlc.exe", "%ProgramFiles%\\VideoLAN\\VLC\\vlc.exe"),
  record("Notepad++", "8.7.8", "Utilities", "exe", "apps/utilities", "A source code and text editor.", false, "10.0.17763", "x64, arm64", "notepad++.exe", "%ProgramFiles%\\Notepad++\\notepad++.exe"),
  record("Git", "2.48.1", "Utilities", "nupkg", "tools", "Distributed version control tools.", true, "10.0.17763", "x64, arm64", "git.exe", "%ProgramFiles%\\Git\\cmd\\git.exe"),
  record("PowerToys", "0.89.0", "Utilities", "msix", "apps/utilities", "Utilities for power users.", false, "10.0.22621", "x64, arm64", "PowerToys.exe", "%LocalAppData%\\PowerToys\\PowerToys.exe"),
];

function fileStem(r: PackageRecord): string {
  return `${r.name.replace(/\W/g, "")}-${r.version}`;
}

export function relativePath(r: PackageRecord): string {
  return `pkgsinfo/${r.directory}/${fileStem(r)}.yaml`;
}

export function installerItem(r: PackageRecord): string {
  return `pkgs/${r.directory}/${fileStem(r)}.${r.type}`;
}

export function changedFields(original: PackageRecord, current: PackageRecord): EditableField[] {
  return EDITABLE_FIELDS.filter((field) => original[field] !== current[field]);
}
