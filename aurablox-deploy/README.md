# AURABLOX Firebase Deployment

This directory contains the standalone Firebase hosting setup for the AURABLOX website.

## Setup

1. **Install Firebase CLI** (if not already installed):
   ```bash
   npm install -g firebase-tools
   ```

2. **Login to Firebase**:
   ```bash
   firebase login
   ```

3. **Use Existing Firebase Project**:
   - Your existing project "daedalus-9f477" will be used
   - Ensure Firebase Hosting is enabled for the project

4. **Initialize Firebase** (optional - if you want to link locally):
   ```bash
   firebase use daedalus-9f477
   ```

## Deployment

Run the deployment script:
```bash
./deploy.sh
```

Or deploy manually:
```bash
firebase deploy --only hosting
```

## Project Structure

```
aurablox-deploy/
├── index.html          # AURABLOX website (formerly aurablox.html)
├── images/            # Supporting images
├── firebase.json      # Firebase hosting configuration
├── .firebaserc       # Firebase project configuration
├── deploy.sh         # Deployment script
└── README.md         # This file
```

## Live Site

After deployment, your AURABLOX site will be available at:
`https://daedalus-9f477.web.app/`

## Customization

- Edit `index.html` to modify the AURABLOX website content
- Add images to the `images/` directory as needed
- The site uses Tailwind CSS CDN, so no build process is required

## Support

For Firebase hosting issues, visit:
[Firebase Hosting Documentation](https://firebase.google.com/docs/hosting)
