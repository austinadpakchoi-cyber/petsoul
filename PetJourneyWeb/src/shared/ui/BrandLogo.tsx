import logo from "./assets/petsoul-logo.png";
import "./brand-logo.css";

/** The supplied wordmark keeps its original colours and transparent artwork. */
export function BrandLogo({ size = "standard" }: {
  size?: "standard" | "welcome" | "compact";
}) {
  return (
    <span className={`ps-brand-logo ps-brand-logo--${size}`}>
      <img src={logo} alt="PetSoul" width={2172} height={724} decoding="async" />
    </span>
  );
}
