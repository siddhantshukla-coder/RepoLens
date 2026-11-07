// Lens.jsx - the lens artwork used on every screen.
// <Sprite/> is mounted once in App and defines the drawings; <Lens/> and <Mark/> just reuse them.
// (Defining them once means unmounting a screen never breaks the gradient of another.)

export function Sprite() {
  return (
    <svg width="0" height="0" style={{ position: 'absolute' }} aria-hidden="true">
      {/* big lens: glass disc, rings, crosshair ticks and a glint */}
      <symbol id="lens" viewBox="0 0 200 200">
        <defs>
          <radialGradient id="glass" cx="35%" cy="30%" r="75%">
            <stop offset="0" stopColor="#55d8ff" stopOpacity=".5" />
            <stop offset=".5" stopColor="#3a4fd8" stopOpacity=".16" />
            <stop offset="1" stopColor="#050811" stopOpacity="0" />
          </radialGradient>
        </defs>
        <circle cx="100" cy="100" r="88" fill="url(#glass)" stroke="#55d8ff" strokeOpacity=".55" strokeWidth="1.5" />
        <circle cx="100" cy="100" r="68" fill="none" stroke="#8a7dff" strokeOpacity=".4" />
        <circle cx="100" cy="100" r="44" fill="none" stroke="#dce9ff" strokeOpacity=".22" strokeDasharray="2 6" />
        <circle cx="100" cy="100" r="4" fill="#55d8ff" />
        <path d="M100 4v22M100 174v22M4 100h22M174 100h22" stroke="#55d8ff" strokeOpacity=".55" strokeWidth="1.5" />
        <path d="M48 70a60 60 0 0 1 42-36" fill="none" stroke="#fff" strokeOpacity=".75" strokeWidth="3" strokeLinecap="round" />
      </symbol>
      {/* small magnifier used as the logo */}
      <symbol id="mark" viewBox="0 0 32 32">
        <circle cx="14" cy="14" r="9" fill="none" stroke="#55d8ff" strokeWidth="2.5" />
        <path d="M21 21l8 8" stroke="#8a7dff" strokeWidth="3" strokeLinecap="round" />
        <path d="M9 11a6 6 0 0 1 4-3" fill="none" stroke="#fff" strokeOpacity=".8" strokeWidth="1.8" strokeLinecap="round" />
      </symbol>
    </svg>
  );
}

// size = width/height in px. The CSS makes it "come into focus" each time a screen appears.
export function Lens({ size }) {
  return (
    <svg className="lens" style={size ? { '--s': size + 'px' } : undefined}>
      <use href="#lens" />
    </svg>
  );
}

export function Mark() {
  return <svg><use href="#mark" /></svg>;
}
