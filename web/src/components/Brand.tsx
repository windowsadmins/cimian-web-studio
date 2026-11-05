import { Icon } from "./Icon";

/** The studio's mark in the top bar. Platform-specific. */
export function Brand() {
  return (
    <div className="mark" aria-hidden="true">
      <Icon name="package" />
    </div>
  );
}
