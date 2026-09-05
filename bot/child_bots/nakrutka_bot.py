from .base import ChildBot


class NakrutkaBot(ChildBot):
    """
    SMM xizmatlarini sotish boti. Haqiqiy SMM panel API ulanmagan holatda
    buyurtmalar owner'ga yuboriladi (qo'lda bajarish uchun). Owner keyinchalik
    haqiqiy SMM-panel API kalitini bersa, avtomatlashtirish qo'shiladi.
    settings["services"] = [{"name": "Instagram followers", "price_per_100": 5000}, ...]
    """

    async def handle_update(self, update: dict) -> None:
        message = update.get("message")
        callback = update.get("callback_query")
        services = self.settings.get("services", [])

        if callback:
            chat_id = callback["from"]["id"]
            data = callback["data"]
            if data.startswith("nakrutka:order:"):
                idx = int(data.split(":")[2])
                service = services[idx]
                await self.answer_callback(callback["id"])
                await self.send_message(
                    chat_id,
                    f"📦 <b>{service['name']}</b>\n"
                    f"💵 Narx: {service['price_per_100']:,} so'm / 100 ta\n\n"
                    f"Miqdorni va havolangizni (profil/post) yozib yuboring, "
                    f"masalan: 500 ta https://instagram.com/username".replace(",", " "),
                )
            return

        if not message:
            return

        chat_id = message["chat"]["id"]
        text = (message.get("text") or "").strip()

        if text == "/start":
            if not services:
                await self.send_message(chat_id, "⚠️ Xizmatlar hali sozlanmagan.")
                return
            buttons = [
                [{"text": f"{s['name']} — {s['price_per_100']:,} so'm/100".replace(",", " "),
                  "callback_data": f"nakrutka:order:{i}"}]
                for i, s in enumerate(services)
            ]
            await self.call_api(
                "sendMessage", chat_id=chat_id,
                text="🚀 <b>SMM xizmatlari</b>\n\nXizmatni tanlang:",
                parse_mode="HTML",
                reply_markup={"inline_keyboard": buttons},
            )
            return

        owner_id = self.settings.get("owner_telegram_id")
        if owner_id and chat_id != owner_id and text:
            await self.send_message(
                owner_id,
                f"🆕 <b>Yangi Nakrutka buyurtma</b> (user {chat_id}):\n{text}",
            )
            await self.send_message(chat_id, "✅ Buyurtmangiz qabul qilindi, tez orada bajariladi.")
