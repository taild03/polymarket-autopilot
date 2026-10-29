import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Polymarket Autopilot - Sổ Theo Dõi Quỹ Tự Động",
  description:
    "Bảng theo dõi danh mục đầu tư tự động trên Polymarket. Rõ ràng, minh bạch, giải thích bằng ngôn ngữ dễ hiểu.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="vi">
      <body className="min-h-[100dvh] bg-[#F7F6F3] text-[#111111] antialiased selection:bg-[#111111] selection:text-[#FFFFFF]">
        {children}
      </body>
    </html>
  );
}
