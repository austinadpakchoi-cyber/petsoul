import "./identity.css";

/** 第一批入口的同一视觉节奏：开场影片之后，每一步都像翻开同一本生活手册。 */
export function EntryHeading({ step, kicker, title, description }: { step?: 1 | 2 | 3 | 4; kicker: string; title: string; description: string }) {
  return (
    <header className="ps-entry-heading">
      <div className="ps-entry-heading__top">
        <span className="ps-entry-heading__brand">PetSoul <span aria-hidden="true">✳</span></span>
        <span className="ps-entry-heading__kicker">{kicker}</span>
      </div>
      <h1>{title}</h1>
      <p>{description}</p>
      {step ? (
        <div className="ps-entry-heading__steps" role="img" aria-label={`入住准备第 ${step} 步，共 4 步`}>
          {[1, 2, 3, 4].map((item) => <span key={item} className={item <= step ? "is-active" : ""} />)}
        </div>
      ) : null}
    </header>
  );
}
