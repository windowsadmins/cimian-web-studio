import { Icon } from "./Icon";

export function ManifestView() {
  return (
    <section aria-label="Manifest workspace">
      <article className="manifest-content">
        <div className="object-title">
          <div className="app-icon" aria-hidden="true">
            <Icon name="manifest" />
          </div>
          <div>
            <h2>Site / Design lab</h2>
            <div className="object-path">manifests/site/design-lab.yaml</div>
          </div>
        </div>
        <section className="editor-section">
          <h3>Catalogs</h3>
          <ol>
            <li>Testing</li>
            <li>Production</li>
          </ol>
          <p className="muted">Order is preserved. Earlier catalogs take precedence.</p>
        </section>
        <section className="editor-section">
          <h3>Included manifests</h3>
          <ul className="manifest-list">
            <li>site_default <small>12 items</small></li>
            <li>common_browsers <small>3 items</small></li>
          </ul>
        </section>
        <section className="editor-section">
          <h3>Managed installs</h3>
          <ul className="manifest-list">
            <li>firefox <small>All clients</small></li>
            <li>vlc <small>All clients</small></li>
          </ul>
        </section>
        <section className="editor-section">
          <h3>Conditional items</h3>
          <ul className="manifest-list">
            <li>
              <span><span className="condition">When</span> hostname contains 'LAB-'</span>
              <small>blender, inkscape</small>
            </li>
            <li>
              <span><span className="condition">When</span> arch == arm64</span>
              <small>vscode-arm64</small>
            </li>
            <li>
              <span><span className="condition">When</span> fact department == IT</span>
              <small>remote-desktop-manager</small>
            </li>
          </ul>
        </section>
        <p className="summary-note">Sample manifest. Repository data arrives with the read API.</p>
      </article>
    </section>
  );
}
