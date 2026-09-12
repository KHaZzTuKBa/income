export function LoadingScreen({ label = "Загрузка…" }: { label?: string }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-paper text-moss">
      <p className="text-sm tracking-wide">{label}</p>
    </div>
  );
}
