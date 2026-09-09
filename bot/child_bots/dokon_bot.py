import json
from datetime import datetime

from database.db import get_session
from .base import ChildBot


def _parse_products(raw_lines: list[str]) -> list[dict]:
    """Format: Nomi|Narxi|Tavsif"""
    products = []
    for line in raw_lines:
        parts = [p.strip() for p in line.split("|")]
        if len(parts) >= 2 and parts[1].isdigit():
            products.append({
                "name": parts[0],
                "price": int(parts[1]),
                "description": parts[2] if len(parts) > 2 else "",
            })
    return products


class DokonBot(ChildBot):
    """
    To'liq onlayn do'kon: katalog, savat, checkout, buyurtma holati.
    settings["products"] = ["Nomi|Narxi|Tavsif", ...]  (owner Mini App'dan kiritadi)
    settings["carts"] = {user_id: {product_index: qty}}
    settings["orders"] = [{"id", "user_id", "items", "total", "address",
                             "phone", "status", "created_at"}]
    """

    STATES_WAITING_ADDRESS = "waiting_address"
    STATES_WAITING_PHONE = "waiting_phone"

    def _products(self) -> list[dict]:
        return _parse_products(self.settings.get("products", []))

    def _main_menu(self) -> dict:
        return {"inline_keyboard": [
            [{"text": "🛍 Katalog", "callback_data": "shop:catalog"}],
            [{"text": "🧺 Savatim", "callback_data": "shop:cart"}],
            [{"text": "📦 Buyurtmalarim", "callback_data": "shop:orders"}],
            [{"text": "ℹ️ Yordam", "callback_data": "shop:help"}],
        ]}

    async def handle_update(self, update: dict) -> None:
        message = update.get("message")
        callback = update.get("callback_query")
        products = self._products()

        if callback:
            chat_id = callback["from"]["id"]
            data = callback["data"]

            if data == "shop:catalog":
                await self.answer_callback(callback["id"])
                await self._show_catalog(chat_id, products)
            elif data == "shop:cart":
                await self.answer_callback(callback["id"])
                await self._show_cart(chat_id, products)
            elif data == "shop:orders":
                await self.answer_callback(callback["id"])
                await self._show_orders(chat_id)
            elif data == "shop:help":
                await self.answer_callback(callback["id"])
                await self.send_message(chat_id, "ℹ️ Katalogdan mahsulot tanlang, savatga qo'shing, so'ng buyurtma bering.")
            elif data.startswith("shop:add:"):
                idx = int(data.split(":")[2])
                await self._add_to_cart(chat_id, idx, products)
                await self.answer_callback(callback["id"], "✅ Savatga qo'shildi!")
            elif data == "shop:checkout":
                await self.answer_callback(callback["id"])
                await self._start_checkout(chat_id)
            elif data.startswith("shop:orderstatus:") and self.is_admin(chat_id):
                _, _, order_id, status = data.split(":")
                await self._set_order_status(int(order_id), status, callback)
            return

        if not message:
            return

        chat_id = message["chat"]["id"]
        text = (message.get("text") or "").strip()
        cart_state = self.settings.get("checkout_state", {}).get(str(chat_id))

        if text == "/start":
            await self.call_api(
                "sendMessage", chat_id=chat_id,
                text="🛍 <b>Do'konga xush kelibsiz!</b>",
                parse_mode="HTML",
                reply_markup=self._main_menu(),
            )
            return

        if cart_state == self.STATES_WAITING_ADDRESS and text:
            await self._save_checkout_field(chat_id, "address", text)
            self.settings.setdefault("checkout_state", {})[str(chat_id)] = self.STATES_WAITING_PHONE
            await self._persist()
            await self.send_message(chat_id, "📱 Telefon raqamingizni yuboring:")
            return

        if cart_state == self.STATES_WAITING_PHONE and text:
            await self._save_checkout_field(chat_id, "phone", text)
            await self._finalize_order(chat_id, products)
            return

        if text.startswith("/holat") and self.is_admin(chat_id):
            parts = text.split()
            if len(parts) == 3:
                await self._set_order_status_text(int(parts[1]), parts[2], chat_id)

    # ---------------- Katalog / Savat ----------------

    async def _show_catalog(self, chat_id: int, products: list[dict]) -> None:
        if not products:
            await self.send_message(chat_id, "⚠️ Katalog hali bo'sh.")
            return
        for i, p in enumerate(products):
            text = f"🛍 <b>{p['name']}</b>\n💵 {p['price']:,} so'm".replace(",", " ")
            if p["description"]:
                text += f"\n{p['description']}"
            await self.call_api(
                "sendMessage", chat_id=chat_id, text=text, parse_mode="HTML",
                reply_markup={"inline_keyboard": [[{"text": "➕ Savatga qo'shish", "callback_data": f"shop:add:{i}"}]]},
            )

    async def _add_to_cart(self, chat_id: int, idx: int, products: list[dict]) -> None:
        if idx >= len(products):
            return
        carts = self.settings.setdefault("carts", {})
        cart = carts.setdefault(str(chat_id), {})
        cart[str(idx)] = cart.get(str(idx), 0) + 1
        await self._persist()

    async def _show_cart(self, chat_id: int, products: list[dict]) -> None:
        cart = self.settings.get("carts", {}).get(str(chat_id), {})
        if not cart:
            await self.send_message(chat_id, "🧺 Savatingiz bo'sh.")
            return
        lines, total = [], 0
        for idx_str, qty in cart.items():
            p = products[int(idx_str)]
            subtotal = p["price"] * qty
            total += subtotal
            lines.append(f"{p['name']} x{qty} — {subtotal:,} so'm".replace(",", " "))
        text = "🧺 <b>Savatingiz:</b>\n\n" + "\n".join(lines) + f"\n\n💰 Jami: {total:,} so'm".replace(",", " ")
        await self.call_api(
            "sendMessage", chat_id=chat_id, text=text, parse_mode="HTML",
            reply_markup={"inline_keyboard": [[{"text": "✅ Buyurtma berish", "callback_data": "shop:checkout"}]]},
        )

    async def _start_checkout(self, chat_id: int) -> None:
        cart = self.settings.get("carts", {}).get(str(chat_id), {})
        if not cart:
            await self.send_message(chat_id, "🧺 Savatingiz bo'sh.")
            return
        self.settings.setdefault("checkout_state", {})[str(chat_id)] = self.STATES_WAITING_ADDRESS
        await self._persist()
        await self.send_message(chat_id, "📍 Yetkazib berish manzilingizni yuboring:")

    async def _save_checkout_field(self, chat_id: int, field: str, value: str) -> None:
        pending = self.settings.setdefault("checkout_pending", {})
        pending.setdefault(str(chat_id), {})[field] = value
        await self._persist()

    async def _finalize_order(self, chat_id: int, products: list[dict]) -> None:
        cart = self.settings.get("carts", {}).get(str(chat_id), {})
        pending = self.settings.get("checkout_pending", {}).get(str(chat_id), {})

        items, total = [], 0
        for idx_str, qty in cart.items():
            p = products[int(idx_str)]
            subtotal = p["price"] * qty
            total += subtotal
            items.append(f"{p['name']} x{qty}")

        orders = self.settings.setdefault("orders", [])
        order_id = len(orders) + 1
        orders.append({
            "id": order_id, "user_id": chat_id, "items": items, "total": total,
            "address": pending.get("address", ""), "phone": pending.get("phone", ""),
            "status": "yangi", "created_at": datetime.utcnow().isoformat(),
        })

        self.settings.get("carts", {}).pop(str(chat_id), None)
        self.settings.get("checkout_pending", {}).pop(str(chat_id), None)
        self.settings.get("checkout_state", {}).pop(str(chat_id), None)
        await self._persist()

        await self.send_message(
            chat_id,
            f"✅ Buyurtmangiz qabul qilindi! (№{order_id})\n\n💰 Jami: {total:,} so'm".replace(",", " "),
        )

        owner_id = self.settings.get("owner_telegram_id")
        if owner_id:
            await self.send_message(
                owner_id,
                f"🆕 <b>Yangi buyurtma №{order_id}</b>\n\n"
                + "\n".join(items) + f"\n\n💰 {total:,} so'm\n📍 {pending.get('address')}\n📱 {pending.get('phone')}".replace(",", " "),
            )

    async def _show_orders(self, chat_id: int) -> None:
        orders = [o for o in self.settings.get("orders", []) if o["user_id"] == chat_id]
        if not orders:
            await self.send_message(chat_id, "📦 Sizda hali buyurtmalar yo'q.")
            return
        lines = [f"№{o['id']} — {o['status']} — {o['total']:,} so'm".replace(",", " ") for o in orders[-10:]]
        await self.send_message(chat_id, "📦 <b>Buyurtmalaringiz:</b>\n\n" + "\n".join(lines))

    async def _set_order_status_text(self, order_id: int, status: str, admin_chat_id: int) -> None:
        orders = self.settings.get("orders", [])
        for o in orders:
            if o["id"] == order_id:
                o["status"] = status
                await self._persist()
                await self.send_message(admin_chat_id, f"✅ №{order_id} holati: {status}")
                await self.send_message(o["user_id"], f"📦 Buyurtmangiz №{order_id} holati: {status}")
                return
        await self.send_message(admin_chat_id, "❌ Bunday buyurtma topilmadi.")

    async def _persist(self) -> None:
        async with get_session() as session:
            await self.save_settings(session)
            await session.commit()
