# Newsletter Signup - Quick Start Guide 🚀

Get your newsletter signup working in **5 minutes**!

---

## ⚡ 5-Minute Setup

### 1️⃣ Get Gmail App Password (2 minutes)

1. Go to: https://myaccount.google.com/apppasswords
2. Click **"Select app"** → Choose **Mail**
3. Click **"Select device"** → Choose **Other** → Type "APIUI"
4. Click **Generate**
5. **Copy the 16-character password** (e.g., `abcd efgh ijkl mnop`)

> **Note:** You need 2-Step Verification enabled first!

---

### 2️⃣ Create .env File (1 minute)

```bash
# Copy the example file
cp env.example .env

# Edit with your credentials
nano .env  # or use your favorite editor
```

Paste your credentials:
```env
GMAIL_USER=your-email@gmail.com
GMAIL_APP_PASSWORD=abcdefghijklmnop
SEND_ADMIN_NOTIFICATIONS=true
```

Save and exit!

---

### 3️⃣ Install & Start (1 minute)

```bash
# Install dependencies
npm install

# Start the server
npm start
```

You should see:
```
✅ Email transporter ready to send messages
🚀 Frontend server running at http://localhost:8080
```

---

### 4️⃣ Test It! (1 minute)

**Option A: Use the test script**
```bash
node test-newsletter.js your-email@gmail.com
```

**Option B: Use the website**
1. Open http://localhost:8080
2. Scroll to newsletter section
3. Enter your email
4. Click "Subscribe"

**Option C: Use cURL**
```bash
curl -X POST http://localhost:8080/api/signup \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com"}'
```

---

## ✅ Success Checklist

- [ ] Server shows "Email transporter ready"
- [ ] Test returns `"success": true`
- [ ] Welcome email received (check spam!)
- [ ] Admin notification received (if enabled)

---

## 🐛 Quick Fixes

### Server won't start?
```bash
# Check if port 8080 is in use
lsof -i :8080

# Kill the process if needed
kill -9 <PID>

# Restart
npm start
```

### Email not sending?
1. Double-check `.env` file exists (not `env.example`)
2. Verify App Password has no spaces
3. Check server logs for errors
4. Try turning off and on again 😅

### Still not working?
```bash
# Check detailed logs
node server.js

# Test connectivity
node -e "console.log(require('dotenv').config())"
```

---

## 🎉 That's It!

Your newsletter signup is now live!

**What happens when someone subscribes:**
1. ✅ Email validated
2. 📧 Beautiful welcome email sent
3. 🔔 You get notified (optional)
4. 💚 User sees success message

---

## 📚 Next Steps

- ✨ Customize the email template in `server.js`
- 📊 Add analytics tracking
- 🗄️ Store subscribers in a database
- 🚀 Deploy to production

**Full Documentation:** See `NEWSLETTER_SETUP.md`

---

## 💡 Pro Tips

1. **Test with your own email first** to see what subscribers receive
2. **Check spam folder** - first emails often go there
3. **Use a real App Password** - not your Gmail password
4. **Keep .env file secret** - never commit it to git

---

**Need Help?** Check `NEWSLETTER_SETUP.md` for detailed troubleshooting!

**Last Updated:** October 12, 2025

