// ─────────────────────────────────────────────
//  TapTech Contact API  –  Secure Serverless Route
//  Vercel serverless function: /api/contact
// ─────────────────────────────────────────────
import nodemailer from "nodemailer";

// ── Simple in-memory rate limiter ─────────────
// Resets on cold-start; good enough for a landing page.
// For high traffic upgrade to Upstash Redis KV.
const rateMap = new Map();
const RATE_LIMIT = 5;          // max submissions per IP
const RATE_WINDOW = 60 * 60 * 1000; // 1 hour window

function checkRateLimit(ip) {
  const now = Date.now();
  const entry = rateMap.get(ip);

  if (!entry || now - entry.start > RATE_WINDOW) {
    rateMap.set(ip, { count: 1, start: now });
    return true;
  }
  if (entry.count >= RATE_LIMIT) return false;
  entry.count++;
  return true;
}

// ── Input sanitizer ──────────────────────────
function sanitize(str = "", maxLen = 1000) {
  return String(str)
    .replace(/[<>"'`]/g, "")   // strip HTML-dangerous chars
    .replace(/\r?\n/g, " ")    // flatten to single line (except message)
    .trim()
    .slice(0, maxLen);
}

function sanitizeMessage(str = "", maxLen = 3000) {
  return String(str)
    .replace(/[<>"'`]/g, "")
    .trim()
    .slice(0, maxLen);
}

// ── Email validation ─────────────────────────
const EMAIL_RE = /^[^\s@]{1,64}@[^\s@]{1,255}\.[^\s@]{2,}$/;

// ── Main handler ─────────────────────────────
export default async function handler(req, res) {
  // ── CORS ──────────────────────────────────
  const allowedOrigin = process.env.ALLOWED_ORIGIN || "*";
  res.setHeader("Access-Control-Allow-Origin", allowedOrigin);
  res.setHeader("Access-Control-Allow-Methods", "POST, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");
  res.setHeader("X-Content-Type-Options", "nosniff");

  if (req.method === "OPTIONS") return res.status(204).end();
  if (req.method !== "POST")
    return res.status(405).json({ error: "Method not allowed." });

  // ── Rate limiting ─────────────────────────
  const ip =
    req.headers["x-forwarded-for"]?.split(",")[0].trim() ||
    req.socket?.remoteAddress ||
    "unknown";

  if (!checkRateLimit(ip)) {
    return res
      .status(429)
      .json({ error: "Too many requests. Please try again in an hour." });
  }

  // ── Parse body ────────────────────────────
  let body = req.body;
  if (typeof body === "string") {
    try { body = JSON.parse(body); } catch { body = {}; }
  }
  const { name, email, phone, service, message, _hp } = body || {};

  // ── Honeypot (invisible field; bots fill it, humans don't) ──
  if (_hp) {
    // Silently pretend success so bots don't retry
    return res.status(200).json({ success: true });
  }

  // ── Required field validation ─────────────
  if (!name || !email || !message) {
    return res
      .status(400)
      .json({ error: "Name, email, and message are required." });
  }

  if (!EMAIL_RE.test(email)) {
    return res.status(400).json({ error: "Please enter a valid email address." });
  }

  // ── Sanitize ──────────────────────────────
  const cleanName    = sanitize(name, 120);
  const cleanEmail   = email.trim().toLowerCase().slice(0, 254);
  const cleanPhone   = sanitize(phone || "Not provided", 30);
  const cleanService = sanitize(service || "Not specified", 120);
  const cleanMsg     = sanitizeMessage(message, 3000);

  // ── Send email via Gmail SMTP ─────────────
  try {
    const transporter = nodemailer.createTransport({
      host: "smtp.gmail.com",
      port: 587,
      secure: false,
      auth: {
        user: process.env.GMAIL_USER,
        pass: process.env.GMAIL_APP_PASSWORD,
      },
    });

    await transporter.sendMail({
      from: `"TapTech Website" <${process.env.GMAIL_USER}>`,
      to: process.env.GMAIL_USER,
      replyTo: cleanEmail,
      subject: `New TapTech Lead: ${cleanName}`,
      html: `
        <!DOCTYPE html>
        <html>
        <body style="font-family:sans-serif;background:#0a0a0f;color:#e8e8ef;padding:32px;">
          <div style="max-width:560px;margin:0 auto;background:#12121a;border-radius:16px;padding:32px;border:1px solid rgba(255,255,255,0.08);">
            <h2 style="color:#00e5a0;margin-bottom:24px;">🎉 New TapTech Lead</h2>
            <table style="width:100%;border-collapse:collapse;">
              <tr><td style="padding:10px 0;color:#8888a0;width:130px;vertical-align:top;">Name</td>
                  <td style="padding:10px 0;font-weight:600;">${cleanName}</td></tr>
              <tr><td style="padding:10px 0;color:#8888a0;vertical-align:top;">Email</td>
                  <td style="padding:10px 0;"><a href="mailto:${cleanEmail}" style="color:#00b8ff;">${cleanEmail}</a></td></tr>
              <tr><td style="padding:10px 0;color:#8888a0;vertical-align:top;">Phone</td>
                  <td style="padding:10px 0;">${cleanPhone}</td></tr>
              <tr><td style="padding:10px 0;color:#8888a0;vertical-align:top;">Package</td>
                  <td style="padding:10px 0;">${cleanService}</td></tr>
              <tr><td style="padding:10px 0;color:#8888a0;vertical-align:top;">Message</td>
                  <td style="padding:10px 0;white-space:pre-wrap;">${cleanMsg}</td></tr>
            </table>
            <hr style="border-color:rgba(255,255,255,0.06);margin:24px 0;">
            <p style="color:#8888a0;font-size:12px;">Sent from taptechconnect.com · IP: ${ip}</p>
          </div>
        </body>
        </html>
      `,
    });

    return res.status(200).json({ success: true });
  } catch (err) {
    console.error("[contact] email error:", err.message);
    return res
      .status(500)
      .json({ error: "Could not send your message. Please email us directly." });
  }
}
