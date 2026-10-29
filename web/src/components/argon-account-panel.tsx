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
    <section className="rounded-[8px] border border-[#EAEAEA] bg-white p-5 shadow-[0_1px_2px_rgba(0,0,0,0.03)] sm:p-6">
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        {/* Left 7 cols: Dual Google Argon Failover Accounts */}
        <div className="lg:col-span-7">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h2 className="text-[15px] font-semibold text-[#111111]">
                2 Tài khoản Google Argon (Tự động đổi nick khi hết lượt)
              </h2>
              <p className="mt-0.5 text-[12.5px] text-[#787774]">
                Khi nick đang dùng chạm giới hạn Quota, máy tự động chuyển sang nick còn lại để không bị ngắt quãng
              </p>
            </div>
            <button
              type="button"
              disabled={meta.isPending}
              onClick={() => actions.switchArgonAccount("failover")}
              className="rounded-[6px] border border-[#EAEAEA] bg-[#FAF9F6] px-3 py-1.5 text-[12px] font-medium text-[#111111] transition-colors hover:bg-[#F0EFEA] disabled:opacity-50 cursor-pointer"
            >
              Thử đổi nick dự phòng
            </button>
          </div>

          <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
            {/* Slot 1 */}
            <div
              className={`rounded-[6px] border p-3.5 transition-colors ${
                activeSlot === "account_1"
                  ? "border-[#111111] bg-[#FAF9F6]"
                  : "border-[#EAEAEA] bg-white"
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="text-[13px] font-semibold text-[#111111]">
                  Nick Google #1 (Chính)
                </span>
                <span
                  className={`rounded-[4px] px-2 py-0.5 text-[11px] font-medium ${
                    activeSlot === "account_1"
                      ? "bg-[#EDF3EC] text-[#346538]"
                      : "bg-[#F4F3EF] text-[#787774]"
                  }`}
                >
                  {activeSlot === "account_1" ? "Đang chạy" : "Đang chờ"}
                </span>
              </div>
              <p className="mt-1 text-[12px] text-[#787774] tabular-nums">
                Đã phân tích thành công: {acc1?.calls_succeeded ?? 0} lần • Hết lượt: {acc1?.quota_hits ?? 0} lần
              </p>
              {activeSlot !== "account_1" && (
                <button
                  type="button"
                  disabled={meta.isPending}
                  onClick={() => actions.switchArgonAccount("account_1")}
                  className="mt-2.5 text-[12px] font-medium text-[#1F6C9F] hover:underline cursor-pointer"
                >
                  Chuyển sang dùng Nick #1
                </button>
              )}
            </div>

            {/* Slot 2 */}
            <div
              className={`rounded-[6px] border p-3.5 transition-colors ${
                activeSlot === "account_2"
                  ? "border-[#111111] bg-[#FAF9F6]"
                  : "border-[#EAEAEA] bg-white"
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="text-[13px] font-semibold text-[#111111]">
                  Nick Google #2 (Dự phòng)
                </span>
                <span
                  className={`rounded-[4px] px-2 py-0.5 text-[11px] font-medium ${
                    activeSlot === "account_2"
                      ? "bg-[#EDF3EC] text-[#346538]"
                      : "bg-[#F4F3EF] text-[#787774]"
                  }`}
                >
                  {activeSlot === "account_2" ? "Đang chạy" : "Sẵn sàng trực"}
                </span>
              </div>
              <p className="mt-1 text-[12px] text-[#787774] tabular-nums">
                Đã phân tích thành công: {acc2?.calls_succeeded ?? 0} lần • Hết lượt: {acc2?.quota_hits ?? 0} lần
              </p>
              {activeSlot !== "account_2" && (
                <button
                  type="button"
                  disabled={meta.isPending}
                  onClick={() => actions.switchArgonAccount("account_2")}
                  className="mt-2.5 text-[12px] font-medium text-[#1F6C9F] hover:underline cursor-pointer"
                >
                  Chuyển sang dùng Nick #2
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Right 5 cols: Backend Server Connection */}
        <div className="border-t border-[#EAEAEA] pt-5 lg:col-span-5 lg:border-l lg:border-t-0 lg:pl-6 lg:pt-0">
          <h2 className="text-[15px] font-semibold text-[#111111]">
            Nguồn dữ liệu máy chủ
          </h2>
          <p className="mt-0.5 text-[12.5px] text-[#787774]">
            Mặc định trang web tự đồng bộ trực tiếp không cần cài đặt. Nếu bạn mở trên Vercel và muốn nối về máy tính cá nhân, nhập địa chỉ vào ô dưới:
          </p>

          <form onSubmit={handleSaveApi} className="mt-3.5 flex gap-2">
            <input
              type="text"
              value={urlDraft}
              onChange={(e) => setUrlDraft(e.target.value)}
              placeholder="Mặc định: Tự động (Hoặc nhập http://localhost:8080)"
              className="flex-1 rounded-[6px] border border-[#EAEAEA] bg-[#FAF9F6] px-3 py-2 text-[12.5px] text-[#111111] placeholder:text-[#787774] focus:border-[#111111] focus:bg-white focus:outline-none"
            />
            <button
              type="submit"
              className="rounded-[6px] border border-[#EAEAEA] bg-white px-3.5 py-2 text-[12.5px] font-medium text-[#111111] hover:bg-[#FAF9F6] cursor-pointer"
            >
              {savedNotice ? "Đã lưu" : "Lưu"}
            </button>
          </form>

          <div className="mt-2.5 flex items-center justify-between text-[11.5px] text-[#787774]">
            <span>
              Chế độ hiện tại:{" "}
              <strong className="font-medium text-[#111111]">
                {customApiUrl ? `Máy chủ riêng (${customApiUrl})` : "Tự động đồng bộ (Mặc định)"}
              </strong>
            </span>
            <span>Số lần tự đổi nick: {router?.total_switches ?? 0}</span>
          </div>
        </div>
      </div>
    </section>
  );
}
