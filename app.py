import asyncio
import logging
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters,
)
from telegram.request import HTTPXRequest

from config import (
    TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, REQUIRE_SEND_CONFIRMATION,
    SEND_DELAY_SECONDS, DAILY_SEND_CAP, SPACE_HOST, WEBHOOK_PORT, USE_WEBHOOK,
)
from db import Session, Lead, sent_today, bump_sent
from agent import draft_email
from leads import find_leads
from mailer import send_email
from brain import route
from gservices import append_leads_to_sheet, create_calendar_event
from datetimeparse import parse_when

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("hermes")


def _auth(update: Update) -> bool:
    return bool(update.effective_chat) and update.effective_chat.id == TELEGRAM_CHAT_ID


def _store_leads(leads: list[dict]) -> int:
    added = 0
    with Session() as s:
        for l in leads:
            if s.query(Lead).filter_by(email=l["email"]).first():
                continue
            s.add(Lead(**l)); added += 1
        s.commit()
    return added


def _valid_iso(v: str | None) -> bool:
    if not v:
        return False
    try:
        datetime.fromisoformat(v); return True
    except Exception:
        return False


async def start(update, ctx):
    if not _auth(update): return
    await update.message.reply_text(
        "Hermes pripravljen. Piši mi normalno (SL/EN) ali uporabi ukaze:\n"
        "/find niša | lokacija\n/draft <ponudba>\n/preview\n"
        "/sendall\n/sheet\n/stats")


async def find_cmd(update, ctx):
    if not _auth(update): return
    arg = " ".join(ctx.args)
    if "|" not in arg:
        return await update.message.reply_text("Uporaba: /find niša | lokacija")
    niche, location = [x.strip() for x in arg.split("|", 1)]
    await update.message.reply_text(f"Iščem: {niche} v {location} …")
    leads = await asyncio.to_thread(find_leads, niche, location)
    added = await asyncio.to_thread(_store_leads, leads)
    await update.message.reply_text(f"Najdenih {len(leads)}, novih shranjenih: {added}.")
    if leads:
        try:
            res = await asyncio.to_thread(append_leads_to_sheet, leads)
            url = res.get("url", "")
            await update.message.reply_text("Dodano v Google tabelo. ✅" + (f"\n{url}" if url else ""))
        except Exception as e:
            await update.message.reply_text(f"Tabela ni uspela: {e}")


async def draft_cmd(update, ctx):
    if not _auth(update): return
    offer = " ".join(ctx.args) or "kratka predstavitev sodelovanja"
    with Session() as s:
        news = s.query(Lead).filter_by(status="new").limit(50).all()
        if not news:
            return await update.message.reply_text("Ni novih leadov. Najprej /find.")
        for lead in news:
            d = await asyncio.to_thread(draft_email, {
                "name": lead.name, "website": lead.website,
                "niche": lead.niche, "location": lead.location}, offer)
            lead.draft_subject = d["subject"]; lead.draft_body = d["body"]
            lead.status = "drafted"
        s.commit(); count = len(news)
    await update.message.reply_text(f"Pripravljenih {count} osnutkov. /preview za ogled.")


async def preview_cmd(update, ctx):
    if not _auth(update): return
    with Session() as s:
        lead = s.query(Lead).filter_by(status="drafted").first()
        if not lead:
            return await update.message.reply_text("Ni osnutkov.")
        txt = (f"📧 {lead.name} <{lead.email}>\n"
               f"Zadeva: {lead.draft_subject}\n\n{lead.draft_body}")
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Pošlji", callback_data=f"send:{lead.id}"),
            InlineKeyboardButton("⏭ Preskoči", callback_data=f"skip:{lead.id}")]])
    await update.message.reply_text(txt, reply_markup=kb)


async def sheet_cmd(update, ctx):
    if not _auth(update): return
    with Session() as s:
        rows = [{"name": l.name, "email": l.email, "website": l.website,
                 "niche": l.niche, "location": l.location, "status": l.status}
                for l in s.query(Lead).all()]
    if not rows:
        return await update.message.reply_text("Ni podatkov za izvoz.")
    try:
        res = await asyncio.to_thread(append_leads_to_sheet, rows)
    except Exception as e:
        return await update.message.reply_text(f"Napaka pri izvozu: {e}")
    url = res.get("url", "")
    await update.message.reply_text(
        f"Vnesel {res.get('count', 0)} vrstic v tabelo." + (f"\n{url}" if url else ""))


async def sendall_cmd(update, ctx):
    if not _auth(update): return
    if REQUIRE_SEND_CONFIRMATION:
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Potrdi", callback_data="bulk:go"),
            InlineKeyboardButton("❌ Prekliči", callback_data="bulk:no")]])
        return await update.message.reply_text("Potrdi pošiljanje VSEH osnutkov?", reply_markup=kb)
    await _do_bulk(ctx)


async def stats_cmd(update, ctx):
    if not _auth(update): return
    with Session() as s:
        def c(st): return s.query(Lead).filter_by(status=st).count()
        msg = (f"Novi: {c('new')}\nOsnutki: {c('drafted')}\nPoslano: {c('sent')}\n"
               f"Napake: {c('failed')}\nPreskočeni: {c('skipped')}\n"
               f"Danes poslano: {sent_today()}/{DAILY_SEND_CAP}")
    await update.message.reply_text(msg)


async def _do_bulk(ctx):
    with Session() as s:
        draft_ids = [l.id for l in s.query(Lead).filter_by(status="drafted").all()]
    sent = fail = 0
    for lid in draft_ids:
        if sent_today() >= DAILY_SEND_CAP:
            await ctx.bot.send_message(TELEGRAM_CHAT_ID, "Dosežena dnevna omejitev."); break
        with Session() as s:
            lead = s.get(Lead, lid)
            if not lead or lead.status != "drafted": continue
            to, subj, body = lead.email, lead.draft_subject, lead.draft_body
        ok, info = await asyncio.to_thread(send_email, to, subj, body)
        with Session() as s:
            lead = s.get(Lead, lid); lead.status = "sent" if ok else "failed"; s.commit()
        if ok: bump_sent(1); sent += 1
        else: fail += 1
        await asyncio.sleep(SEND_DELAY_SECONDS)
    await ctx.bot.send_message(TELEGRAM_CHAT_ID, f"Končano. Poslano: {sent}, napak: {fail}.")


async def on_button(update, ctx):
    if not _auth(update): return
    q = update.callback_query; await q.answer()
    action, lid = q.data.split(":"); lid = int(lid)
    with Session() as s:
        lead = s.get(Lead, lid)
        if not lead: return await q.edit_message_text("Lead ne obstaja.")
        if action == "skip":
            lead.status = "skipped"; s.commit()
            return await q.edit_message_text("Preskočeno.")
        to, subj, body = lead.email, lead.draft_subject, lead.draft_body
    ok, info = await asyncio.to_thread(send_email, to, subj, body)
    with Session() as s:
        lead = s.get(Lead, lid); lead.status = "sent" if ok else "failed"; s.commit()
    if ok: bump_sent(1)
    await q.edit_message_text(f"{'✅ Poslano' if ok else '❌ Napaka'}: {to}\n{info}")


async def on_bulk(update, ctx):
    if not _auth(update): return
    q = update.callback_query; await q.answer()
    _, decision = q.data.split(":")
    if decision == "no":
        return await q.edit_message_text("Preklicano.")
    await q.edit_message_text("Začenjam množično pošiljanje …")
    await _do_bulk(ctx)


async def on_text(update, ctx):
    if not _auth(update): return
    text = update.message.text
    await ctx.bot.send_chat_action(update.effective_chat.id, "typing")
    decision = await asyncio.to_thread(route, text)
    action = decision.get("action", "chat")
    p = decision.get("params", {}) or {}
    reply = decision.get("reply", "")
    if reply:
        await update.message.reply_text(reply)

    if action == "find" and p.get("niche") and p.get("location"):
        leads = await asyncio.to_thread(find_leads, p["niche"], p["location"])
        added = await asyncio.to_thread(_store_leads, leads)
        await update.message.reply_text(f"Najdenih {len(leads)}, novih: {added}.")
        if leads:
            try:
                res = await asyncio.to_thread(append_leads_to_sheet, leads)
                url = res.get("url", "")
                await update.message.reply_text("Dodano v tabelo. ✅" + (f"\n{url}" if url else ""))
            except Exception as e:
                await update.message.reply_text(f"Tabela ni uspela: {e}")
    elif action == "export_sheet":
        with Session() as s:
            rows = [{"name": l.name, "email": l.email, "website": l.website,
                     "niche": l.niche, "location": l.location, "status": l.status}
                    for l in s.query(Lead).all()]
        if not rows:
            return await update.message.reply_text("Ni podatkov za izvoz.")
        try:
            res = await asyncio.to_thread(append_leads_to_sheet, rows)
            url = res.get("url", "")
            await update.message.reply_text(
                f"Vnesel {res.get('count', 0)} vrstic v tabelo." + (f"\n{url}" if url else ""))
        except Exception as e:
            await update.message.reply_text(f"Napaka pri izvozu: {e}")
    elif action == "draft":
        ctx.args = (p.get("offer") or "kratka predstavitev sodelovanja").split()
        await draft_cmd(update, ctx)
    elif action == "preview":
        await preview_cmd(update, ctx)
    elif action == "send_all":
        await sendall_cmd(update, ctx)
    elif action == "create_event":
        start_iso = p.get("start"); end_iso = p.get("end")
        if not _valid_iso(start_iso):
            start_iso, end_iso = await asyncio.to_thread(parse_when, text)
        if not start_iso:
            await update.message.reply_text(
                "Nisem razumel časa dogodka. Poskusi npr. \"jutri ob 15h sestanek\".")
        else:
            try:
                res = await asyncio.to_thread(
                    create_calendar_event, p.get("title", "Sestanek"),
                    start_iso, end_iso, p.get("description", ""), p.get("event_location", ""))
                await update.message.reply_text(
                    f"Dogodek dodan v koledar za {start_iso}. ✅" if res.get("ok")
                    else f"Napaka: {res.get('error')}")
            except Exception as e:
                await update.message.reply_text(f"Napaka pri koledarju: {e}")


def register_handlers(app):
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("find", find_cmd))
    app.add_handler(CommandHandler("draft", draft_cmd))
    app.add_handler(CommandHandler("preview", preview_cmd))
    app.add_handler(CommandHandler("sheet", sheet_cmd))
    app.add_handler(CommandHandler("sendall", sendall_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CallbackQueryHandler(on_bulk, pattern=r"^bulk:"))
    app.add_handler(CallbackQueryHandler(on_button, pattern=r"^(send|skip):"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))


def run_webhook():
    if not SPACE_HOST:
        raise RuntimeError("SPACE_HOST not set (e.g. yourname-hermes.hf.space)")
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    register_handlers(app)
    path = TELEGRAM_TOKEN.split(":")[0]
    url = f"https://{SPACE_HOST}/{path}"
    log.info("Setting webhook: %s", url)
    app.run_webhook(listen="0.0.0.0", port=WEBHOOK_PORT, url_path=path,
                    webhook_url=url, drop_pending_updates=True,
                    allowed_updates=Update.ALL_TYPES)


async def run_polling_async():
    request = HTTPXRequest(connect_timeout=30.0, read_timeout=30.0,
                           write_timeout=30.0, pool_timeout=30.0,
                           connection_pool_size=50)
    gur = HTTPXRequest(connect_timeout=30.0, read_timeout=40.0, pool_timeout=30.0)
    app = (Application.builder().token(TELEGRAM_TOKEN)
           .request(request).get_updates_request(gur).build())
    register_handlers(app)
    last_err = None
    for attempt in range(1, 6):
        try:
            log.info("Initializing (attempt %s)…", attempt)
            await app.initialize()
            me = await app.bot.get_me()
            log.info("Connected as @%s", me.username); last_err = None; break
        except Exception as e:
            last_err = e
            log.warning("Init failed: %s. Retry 5s…", e)
            await asyncio.sleep(5)
    if last_err: raise last_err
    await app.start()
    await app.updater.start_polling(allowed_updates=Update.ALL_TYPES,
                                    drop_pending_updates=True)
    log.info("Hermes is polling.")
    try:
        await asyncio.Event().wait()
    finally:
        await app.updater.stop(); await app.stop(); await app.shutdown()


def main():
    try:
        if USE_WEBHOOK:
            run_webhook()
        else:
            asyncio.run(run_polling_async())
    except (KeyboardInterrupt, SystemExit):
        log.info("Shutting down.")


if __name__ == "__main__":
    main()
