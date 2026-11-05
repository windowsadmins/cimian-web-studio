// How Cimian pkginfo fields are laid out in the editor. The only platform-specific
// part of the packages workspace; every key not listed here appears under Advanced.
// Dotted keys reach into nested dictionaries.

export interface FieldSpec {
  key: string;
  label: string;
  kind?: "text" | "script" | "list";
}
export interface SectionSpec {
  title: string;
  fields: FieldSpec[];
}
export interface TabSpec {
  name: string;
  sections: SectionSpec[];
}

export const PLATFORM = {
  name: "Cimian",
  descriptionLabel: "Shown in Managed Software Center for Windows",
};

// Installer files an import accepts.
export const IMPORT_ACCEPT = ".msi,.exe,.nupkg";

// Manifest keys the manifests workspace edits, in the order it shows them.
export const MANIFEST_INCLUDES = "included_manifests";
export const MANIFEST_SECTIONS = [
  "managed_installs",
  "managed_uninstalls",
  "managed_updates",
  "optional_installs",
  "featured_items",
  "default_installs",
  "managed_profiles",
  "managed_apps",
];

export const TABS: TabSpec[] = [
  {
    name: "Overview",
    sections: [
      {
        title: "Identity",
        fields: [
          { key: "name", label: "Name" },
          { key: "display_name", label: "Display name" },
          { key: "version", label: "Version" },
          { key: "category", label: "Category" },
          { key: "developer", label: "Developer" },
        ],
      },
      { title: "Catalogs", fields: [{ key: "catalogs", label: "Catalogs", kind: "list" }] },
      { title: "Description", fields: [{ key: "description", label: PLATFORM.descriptionLabel, kind: "script" }] },
      {
        title: "Installer",
        fields: [
          { key: "installer.type", label: "Type" },
          { key: "installer.location", label: "Location" },
          { key: "installer.hash", label: "Hash" },
          { key: "installer.arguments", label: "Arguments", kind: "list" },
        ],
      },
      {
        title: "Requirements",
        fields: [
          { key: "minimum_os_version", label: "Minimum Windows build" },
          { key: "maximum_os_version", label: "Maximum Windows build" },
          { key: "supported_architectures", label: "Architectures", kind: "list" },
        ],
      },
    ],
  },
  {
    name: "Detection",
    sections: [
      { title: "Installs", fields: [{ key: "installs", label: "Items", kind: "list" }] },
      {
        title: "Check scripts",
        fields: [
          { key: "installcheck_script", label: "Install check", kind: "script" },
          { key: "uninstallcheck_script", label: "Uninstall check", kind: "script" },
        ],
      },
    ],
  },
  {
    name: "Install",
    sections: [
      {
        title: "Behavior",
        fields: [
          { key: "unattended_install", label: "Unattended install" },
          { key: "blocking_applications", label: "Blocking applications", kind: "list" },
          { key: "restart_action", label: "Restart action" },
        ],
      },
      {
        title: "Scripts",
        fields: [
          { key: "preinstall_script", label: "Preinstall", kind: "script" },
          { key: "postinstall_script", label: "Postinstall", kind: "script" },
        ],
      },
    ],
  },
  {
    name: "Uninstall",
    sections: [
      {
        title: "Removal",
        fields: [
          { key: "uninstallable", label: "Uninstallable" },
          { key: "unattended_uninstall", label: "Unattended uninstall" },
          { key: "uninstaller", label: "Uninstallers", kind: "list" },
        ],
      },
      {
        title: "Scripts",
        fields: [
          { key: "preuninstall_script", label: "Preuninstall", kind: "script" },
          { key: "postuninstall_script", label: "Postuninstall", kind: "script" },
        ],
      },
    ],
  },
  {
    name: "Advanced",
    sections: [
      {
        title: "Dependencies",
        fields: [
          { key: "requires", label: "Requires", kind: "list" },
          { key: "update_for", label: "Update for", kind: "list" },
        ],
      },
    ],
  },
];
