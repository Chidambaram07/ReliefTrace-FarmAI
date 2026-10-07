export default function Pill({ tone, children }) {
  return <span className={`pill ${tone}`}>{children}</span>
}
