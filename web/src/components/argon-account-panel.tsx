"use client";

import React, { useState } from "react";
import { useAutopilot } from "./autopilot-provider";

export function ArgonAccountPanel() {
  const { state, actions, meta } = useAutopilot();
  const { data, customApiUrl } = state;
  const [urlDraft, setUrlDraft] = useState(customApiUrl);
  const [savedNotice, setSavedNotice] = useState(false);

  const router = data.ai_summary?.account_router;
  const activeSlot = router?.active_slot ?? "account_1";
  const acc1 = router?.accounts?.account_1;
  const acc2 = router?.accounts?.account_2;

  const handleSaveApi = (e: React.FormEvent) => {
    e.preventDefault();
    actions.setCustomApiUrl(urlDraft);
    setSavedNotice(true);
    setTimeout(() => setSavedNotice(false), 2500);
  };

  return (
    <section className="rounded-[20px] border-2 border-[#111111] bg-white p-6 shadow-[6px_6px_0px_#111111] sm:p-8">
      <div className="grid grid-cols-1 gap-8 lg:grid-cols-12">
        {/* Left 7 cols: Dual Google Argon Failover Accounts */}
        <div className="lg:col-span-7">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="font-display text-[20px] font-bold uppercase tracking-[-0.02em] text-[#111111] sm:text-[24px]">
                2 TÀI KHOẢN GOOGLE ARGON DỰ PHÒNG
              </h2>
              <p className="mt-1 text-[15px] font-semibold text-[#52514E]">
                Khi nick đang chạy hết lượt Quota, máy tự động nhảy sang nick còn lại trong 1 giây
              </p>
            </div>
            <button
              type="button"
              disabled={meta.isPending}
              onClick={() => actions.switchArgonAccount("failover")}
              className="rounded-[10px] border-2 border-[#111111] bg-[#FFD166] px-4 py-2.5 text-[14px] font-extrabold uppercase text-[#111111] shadow-[3px_3px_0px_#111111] transition-all hover:translate-x-[1px] hover:translate-y-[1px] hover:shadow-[1px_1px_0px_#111111] disabled:opacity-50 cursor-pointer"
            >
              ĐỔI NICK DỰ PHÒNG NGAY
            </button>
          </div>

          <div className="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-2">
            {/* Slot 1 */}
            <div
              className={`rounded-[14px] border-2 border-[#111111] p-4 shadow-[4px_4px_0px_#111111] ${
                activeSlot === "account_1" ? "bg-[#B8F397]" : "bg-[#FAF8F5]"
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="rounded-[6px] bg-[#111111] px-2.5 py-1 text-[12px] font-extrabold uppercase text-white">
                  {activeSlot === "account_1" ? "ĐANG CHẠY CHÍNH" : "ĐANG TRỰC CHỜ"}
                </span>
                <span className="text-[12px] font-extrabold uppercase text-[#111111]">
                  ĐÃ LƯU KHÓA: {acc1?.configured ? "CÓ" : "CHƯA"}
                </span>
              </div>
              <div className="mt-3 text-[16px] font-extrabold text-[#111111] break-all">
                {acc1?.label || "Nick Google #1 (leductai21204@gmail.com)"}
              </div>
              <p className="mt-1.5 text-[14px] font-bold text-[#111111]/80 tabular-nums">
                Đã gọi thành công: {acc1?.calls_succeeded ?? 0} lần • Chạm Quota: {acc1?.quota_hits ?? 0} lần
              </p>
              {activeSlot !== "account_1" && (
                <button
                  type="button"
                  disabled={meta.isPending}
                  onClick={() => actions.switchArgonAccount("account_1")}
                  className="mt-3 w-full rounded-[8px] border-2 border-[#111111] bg-white py-2 text-[13px] font-extrabold uppercase text-[#111111] hover:bg-[#111111] hover:text-white cursor-pointer"
                >
                  BẬT NICK SỐ 1
                </button>
              )}
            </div>

            {/* Slot 2 */}
            <div
              className={`rounded-[14px] border-2 border-[#111111] p-4 shadow-[4px_4px_0px_#111111] ${
                activeSlot === "account_2" ? "bg-[#B8F397]" : "bg-[#FAF8F5]"
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="rounded-[6px] bg-[#111111] px-2.5 py-1 text-[12px] font-extrabold uppercase text-white">
                  {activeSlot === "account_2" ? "ĐANG CHẠY CHÍNH" : "SẴN SÀNG DỰ PHÒNG"}
                </span>
                <span className="text-[12px] font-extrabold uppercase text-[#111111]">
                  ĐÃ LƯU KHÓA: {acc2?.configured ? "CÓ" : "CHƯA"}
                </span>
              </div>
              <div className="mt-3 text-[16px] font-extrabold text-[#111111] break-all">
                {acc2?.label || "Nick Google #2 (taoyeumaygianga@gmail.com)"}
              </div>
              <p className="mt-1.5 text-[14px] font-bold text-[#111111]/80 tabular-nums">
                Đã gọi thành công: {acc2?.calls_succeeded ?? 0} lần • Chạm Quota: {acc2?.quota_hits ?? 0} lần
              </p>
              {activeSlot !== "account_2" && (
                <button
                  type="button"
                  disabled={meta.isPending}
                  onClick={() => actions.switchArgonAccount("account_2")}
                  className="mt-3 w-full rounded-[8px] border-2 border-[#111111] bg-white py-2 text-[13px] font-extrabold uppercase text-[#111111] hover:bg-[#111111] hover:text-white cursor-pointer"
                >
                  BẬT NICK SỐ 2
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Right 5 cols: Backend Server Connection */}
        <div className="border-t-2 border-[#111111] pt-6 lg:col-span-5 lg:border-l-2 lg:border-t-0 lg:pl-8 lg:pt-0">
          <h2 className="font-display text-[20px] font-bold uppercase tracking-[-0.02em] text-[#111111] sm:text-[24px]">
            NGUỒN DỮ LIỆU MÁY CHỦ
          </h2>
          <p className="mt-1 text-[15px] font-semibold text-[#52514E]">
            Trang web tự động đồng bộ mỗi 5 giây. Nếu xem trên Vercel và muốn nối về máy Mac ở nhà, dán địa chỉ vào đây:
          </p>

          <form onSubmit={handleSaveApi} className="mt-4 flex flex-col gap-3 sm:flex-row">
            <input
              type="text"
              value={urlDraft}
              onChange={(e) => setUrlDraft(e.target.value)}
              placeholder="Mặc định: Tự động (Hoặc http://localhost:8080)"
              className="flex-1 rounded-[10px] border-2 border-[#111111] bg-[#FAF8F5] px-4 py-3 text-[15px] font-semibold text-[#111111] placeholder:text-[#787774] focus:bg-white focus:outline-none"
            />
            <button
              type="submit"
              className="rounded-[10px] border-2 border-[#111111] bg-[#111111] px-5 py-3 text-[15px] font-extrabold uppercase text-white shadow-[3px_3px_0px_#FF5C16] hover:bg-[#2B2B2A] cursor-pointer"
            >
              {savedNotice ? "ĐÃ LƯU" : "LƯU KẾT NỐI"}
            </button>
          </form>

          <div className="mt-4 rounded-[10px] border-2 border-[#111111] bg-[#F4F0EA] p-3 text-[14px] font-bold text-[#111111]">
            Đang kết nối:{" "}
            <span className="text-[#FF5C16]">
              {customApiUrl ? customApiUrl : "Tự động đồng bộ trực tiếp (5 giây/lần)"}
            </span>
          </div>
        </div>
      </div>
    </section>
  );
}
