# Firebase Email Functions Deployment Guide

## 🚀 Deploy Email Signups to Firebase

Your email signup system is now ready to deploy to Firebase Cloud Functions!

---

## ✅ What Was Done

### Files Updated for Firebase
1. ✅ `functions/index.js` - Added `/signup` and `/beta-signup` endpoints
2. ✅ `functions/package.json` - Added `nodemailer@6.9.7`
3. ✅ `firebase.json` - Added routing for signup endpoints
4. ✅ Dependencies installed in `functions/`

---

## 🔧 Deployment Steps

### Step 1: Set Firebase Environment Variables

Set your Gmail credentials in Firebase:

```bash
# Set Gmail user
firebase functions:config:set gmail.user="jjohnso75@gmail.com"

# Set Gmail App Password
firebase functions:config:set gmail.app_password="jrngpsjanrfwaapf"
```

Verify configuration:
```bash
firebase functions:config:get
```

Expected output:
```json
{
  "gmail": {
    "user": "jjohnso75@gmail.com",
    "app_password": "jrngpsjanrfwaapf"
  }
}
```

---

### Step 2: Deploy Functions

```bash
# Deploy only functions
firebase deploy --only functions

# Or deploy everything (hosting + functions)
firebase deploy
```

---

### Step 3: Test on Production

Once deployed, test with:

```bash
# Test newsletter signup
curl -X POST https://ai-apiui.web.app/api/signup \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com"}'

# Test beta signup  
curl -X POST https://ai-apiui.web.app/api/beta-signup \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com"}'
```

---

## 🔍 How Firebase Routing Works

### firebase.json Configuration

```json
"rewrites": [
  {
    "source": "/api/signup",
    "function": "chat"
  },
  {
    "source": "/api/beta-signup",
    "function": "chat"
  },
  {
    "source": "/api/**",
    "function": "chat"
  }
]
```

**What This Means:**
- `/api/signup` → Firebase Function `chat` → handles newsletter signups
- `/api/beta-signup` → Firebase Function `chat` → handles beta signups
- `/api/chat` → Firebase Function `chat` → handles MCP chat

All running on the same Cloud Function! 🎯

---

## 🏗️ Architecture

### Local Development
```
Browser → http://localhost:8080/api/signup
              ↓
         server.js (Node.js)
              ↓
         Nodemailer → Gmail SMTP
```

### Firebase Production
```
Browser → https://ai-apiui.web.app/api/signup
              ↓
         Firebase Hosting
              ↓
         Firebase Cloud Function "chat"
              ↓
         Nodemailer → Gmail SMTP
```

---

## 📝 Environment Variables

### Required in Firebase
```bash
gmail.user           # Your Gmail address
gmail.app_password   # Gmail App Password
```

### Optional
```bash
apiui.openai_api_key        # For chat features
apiui.flask_backend_url     # Backend API URL
```

---

## 🧪 Testing Deployment

### 1. Check Function Logs
```bash
firebase functions:log
```

Look for:
```
✅ Email transporter initialized
📧 New newsletter signup: user@example.com
✅ Thank you email sent to: user@example.com
```

### 2. Test in Browser

**Newsletter:**
1. Visit https://ai-apiui.web.app/
2. Scroll to newsletter section
3. Enter email and submit
4. Check inbox

**Beta:**
1. Visit https://ai-apiui.web.app/app.html
2. Fill in beta signup form
3. Submit
4. Check inbox

---

## 🐛 Troubleshooting

### Error: "Email service not configured"

**Problem:** Gmail credentials not set in Firebase

**Solution:**
```bash
firebase functions:config:set gmail.user="your-email@gmail.com"
firebase functions:config:set gmail.app_password="your-app-password"
firebase deploy --only functions
```

### Error: 404 Not Found

**Problem:** Functions not deployed or routing misconfigured

**Solution:**
```bash
# Redeploy everything
firebase deploy

# Check deployment status
firebase functions:list
```

### Emails Not Sending

**Problem:** Invalid Gmail App Password

**Solution:**
1. Generate new App Password at https://myaccount.google.com/apppasswords
2. Update Firebase config:
   ```bash
   firebase functions:config:set gmail.app_password="new-password"
   firebase deploy --only functions
   ```

---

## 📊 Cost Considerations

### Firebase Functions Pricing

**Free Tier Includes:**
- 2 million invocations/month
- 400,000 GB-seconds/month
- 200,000 CPU-seconds/month

**Each email signup uses:**
- ~1-2 seconds execution time
- ~256 MB memory
- Minimal cost (well within free tier for normal usage)

**Estimated Cost:** $0 for < 100,000 signups/month

---

## 🔒 Security Best Practices

### Firebase Configuration
✅ **Never commit** `.env` files  
✅ **Use Firebase config** for secrets (not environment variables in code)  
✅ **Validate all inputs** (email format checking)  
✅ **Rate limiting** (consider adding Firebase rate limiting rules)  

### Recommended Addition
Add rate limiting to `firebase.json`:

```json
"hosting": {
  "appAssociation": "AUTO",
  "rewrites": [...],
  "headers": [{
    "source": "/api/**",
    "headers": [{
      "key": "X-Content-Type-Options",
      "value": "nosniff"
    }]
  }]
}
```

---

## 📈 Monitoring

### View Function Logs
```bash
# Real-time logs
firebase functions:log --only chat

# Recent logs
firebase functions:log --only chat --lines 50
```

### Check Function Health
```bash
# Get function URL
firebase functions:config:get

# Test endpoint
curl https://us-central1-YOUR-PROJECT.cloudfunctions.net/chat/health
```

---

## 🔄 Update Process

When you make changes to email templates:

```bash
# 1. Edit functions/index.js
# 2. Deploy
firebase deploy --only functions

# 3. Test
curl -X POST https://ai-apiui.web.app/api/signup \
  -H "Content-Type: application/json" \
  -d '{"email":"test@gmail.com"}'
```

**No need to redeploy hosting** - email templates are in the function code!

---

## 📁 File Structure

```
/Users/jahflyx/apiui/
├── functions/
│   ├── index.js          ✅ Email endpoints added
│   ├── package.json      ✅ nodemailer added
│   └── node_modules/     ✅ Dependencies installed
├── firebase.json         ✅ Routing configured
├── frontend/
│   ├── index.html        ✅ Calls /api/signup
│   └── app.html          ✅ Calls /api/beta-signup
└── server.js             ✅ Local development server
```

---

## 🎯 Deployment Checklist

Before deploying to production:

- [x] Added email endpoints to `functions/index.js`
- [x] Added nodemailer to `functions/package.json`
- [x] Installed dependencies (`npm install` in functions/)
- [x] Updated `firebase.json` routing
- [ ] Set Firebase config (`firebase functions:config:set`)
- [ ] Deploy functions (`firebase deploy --only functions`)
- [ ] Test newsletter signup on production
- [ ] Test beta signup on production
- [ ] Verify emails arrive
- [ ] Check Firebase function logs

---

## 📧 Email Endpoints

### Production URLs (After Deployment)

**Newsletter:**
```
POST https://ai-apiui.web.app/api/signup
```

**Beta:**
```
POST https://ai-apiui.web.app/api/beta-signup
```

**Health Check:**
```
GET https://us-central1-YOUR-PROJECT.cloudfunctions.net/chat/health
```

---

## 🎊 Quick Deploy Command

```bash
# One command to deploy everything
firebase functions:config:set \
  gmail.user="jjohnso75@gmail.com" \
  gmail.app_password="jrngpsjanrfwaapf" \
  && firebase deploy
```

---

## 📚 Related Documentation

- `NEWSLETTER_SETUP.md` - Initial email setup
- `BETA_SIGNUP_IMPLEMENTATION.md` - Beta system details
- `EMAIL_SYSTEMS_SUMMARY.md` - Overview of both systems
- Firebase Functions docs: https://firebase.google.com/docs/functions

---

**Ready to deploy?** Run the commands above and your email systems will be live on Firebase! 🚀

**Last Updated:** October 12, 2025

