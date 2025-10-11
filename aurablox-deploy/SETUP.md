# AURABLOX Firebase Setup Guide

This guide will help you deploy the AURABLOX website to Firebase Hosting as a standalone site.

## Prerequisites

1. **Firebase Account**: Create a Firebase account at https://console.firebase.google.com/
2. **Node.js & npm**: Ensure you have Node.js and npm installed
3. **Firebase CLI**: Install Firebase CLI globally

## Step 1: Use Existing Firebase Project

1. Go to your existing Firebase project: [daedalus-9f477](https://console.firebase.google.com/u/0/project/daedalus-9f477/overview)
2. Ensure Firebase Hosting is enabled for the project
3. If Firebase Hosting is not enabled, click on "Hosting" in the left sidebar
4. Click "Get started" to enable hosting

## Step 2: Install Firebase CLI

```bash
npm install -g firebase-tools
```

## Step 3: Login to Firebase

```bash
firebase login
```

A browser window will open - sign in with your Google account.

## Step 4: Deploy AURABLOX

### Option A: Use the deployment script
```bash
cd aurablox-deploy
./deploy.sh
```

### Option B: Manual deployment
```bash
cd aurablox-deploy
firebase use aurablox-site
firebase deploy --only hosting
```

## Step 6: Access Your Site

After successful deployment, your AURABLOX site will be available at:
`https://daedalus-9f477.web.app/`

## Troubleshooting

### "Project not found" error
- Make sure you have access to the "daedalus-9f477" Firebase project
- Run `firebase use daedalus-9f477` to select the correct project

### "Not logged in" error
- Run `firebase login` again
- Check that you're logged in with the correct Google account

### Deployment fails
- Check that all files are in the `aurablox-deploy` directory
- Ensure `firebase.json` is properly configured
- Try `firebase deploy --only hosting --debug` for detailed error logs

## Custom Domain (Optional)

To use a custom domain:

1. Go to Firebase Console → Hosting → "Add custom domain"
2. Enter your domain name
3. Follow the DNS setup instructions
4. Your site will be available at your custom domain

## File Structure

```
aurablox-deploy/
├── index.html          # Main AURABLOX page
├── images/            # All supporting images
├── favicon.*          # Favicon files
├── firebase.json      # Firebase configuration
├── .firebaserc       # Project configuration
├── deploy.sh         # Deployment script
├── README.md         # General information
└── SETUP.md          # This setup guide
```

## Updating Your Site

To make changes and redeploy:

1. Edit files in the `aurablox-deploy` directory
2. Run `./deploy.sh` or `firebase deploy --only hosting`
3. Your changes will be live within minutes

## Support

- [Firebase Hosting Documentation](https://firebase.google.com/docs/hosting)
- [Firebase CLI Documentation](https://firebase.google.com/docs/cli)
- [Firebase Console](https://console.firebase.google.com/)
