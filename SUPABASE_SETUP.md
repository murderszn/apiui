# Supabase Setup Guide for ai-apiup

This guide will help you set up Supabase integration for the ai-apiup backend according to the backend-spec.md requirements.

## Prerequisites

1. A Supabase account (sign up at https://supabase.com)
2. A new Supabase project

## Step 1: Create a Supabase Project

1. Go to https://supabase.com and sign in
2. Click "New Project"
3. Fill in your project details:
   - Name: `ai-apiup`
   - Database Password: Choose a strong password
   - Region: Choose the closest region to your users
4. Click "Create new project"

## Step 2: Configure Authentication

### 2.1 Enable Email Authentication

1. In your Supabase dashboard, go to **Authentication > Providers**
2. Find the **Email** provider in the list
3. Click the toggle to **enable** the Email provider
4. The email provider is now active for sign-ups and sign-ins

### 2.2 Configure Authentication Settings (Optional)

1. Go to **Authentication > Settings**
2. Configure the following settings as needed:
   - **Site URL**: `https://your-domain.com` (or `http://localhost:3000` for development)
   - **Redirect URLs**: Add your frontend URLs
   - **JWT Expiry**: Default is usually fine (3600 seconds)
   - **Enable email confirmations**: Toggle based on your preference

## Step 3: Set Up Database

### 3.1 Run the Setup SQL

1. In your Supabase dashboard, go to **SQL Editor**
2. Copy the contents of `supabase-setup.sql` from this repository
3. Paste it into the SQL Editor
4. Click **Run** to execute the SQL commands

This will create:
- The `apis` table with proper columns and RLS policies
- Indexes for performance
- Storage policies for the user-uploads bucket

### 3.2 Verify Table Creation

1. Go to **Table Editor** in your Supabase dashboard
2. You should see the `apis` table with the following columns:
   - `id` (bigint, Primary Key)
   - `created_at` (timestamptz)
   - `user_id` (uuid, Foreign Key to auth.users.id)
   - `api_name` (text)
   - `endpoint_url` (text)
   - `file_path` (text)
   - `status` (text)
   - `deployment_metadata` (jsonb)

## Step 4: Set Up Storage

### 4.1 Create Storage Bucket

1. In your Supabase dashboard, go to **Storage**
2. Click **Create bucket**
3. Enter bucket details:
   - **Name**: `user-uploads`
   - **Public bucket**: **Uncheck** this (keep it private)
4. Click **Create bucket**

### 4.2 Configure Storage Policies

The SQL setup script should have created the necessary storage policies. To verify:

1. Go to **Storage > user-uploads > Policies**
2. You should see policies for:
   - Users can upload their own files
   - Users can view their own files
   - Users can update their own files
   - Users can delete their own files

## Step 5: Get API Keys

### 5.1 Get Project URL and Keys

1. In your Supabase dashboard, go to **Settings > API**
2. Copy the following values:
   - **Project URL**: `https://your-project-ref.supabase.co`
   - **anon/public key**: The public anonymous key
   - **service_role key**: The secret service role key (keep this secure!)

## Step 6: Configure Environment Variables

Update your backend environment variables or configuration:

```bash
# Add these to your .env file or environment
SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_ANON_KEY=your-anon-key-here
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key-here
```

Or update `backend/core/config.py` if you're not using environment variables.

## Step 7: Update Frontend Configuration

Update the Supabase configuration in `frontend/app.html`:

```javascript
// Replace these placeholder values
const supabaseUrl = 'https://your-project-ref.supabase.co';
const supabaseKey = 'your-anon-key-here';
```

## Step 8: Test the Integration

1. Start your backend server
2. Open your frontend application
3. Try signing up with an email and password
4. Verify that user data is stored in Supabase:
   - Check **Authentication > Users** in Supabase dashboard
   - Check the `apis` table for any created APIs

## Troubleshooting

### Common Issues

1. **RLS Policies Not Working**
   - Ensure RLS is enabled on the `apis` table
   - Check that policies are correctly configured
   - Verify user authentication is working

2. **Storage Uploads Failing**
   - Check bucket name is exactly `user-uploads`
   - Verify storage policies are applied
   - Ensure bucket is set to private

3. **Authentication Not Working**
   - Verify anon key is correct
   - Check that Email provider is enabled
   - Ensure site URL is configured correctly

### Debugging

1. Check Supabase logs in the dashboard under **Reports > Logs**
2. Use browser developer tools to check network requests
3. Verify environment variables are loaded correctly

## Security Notes

- Never commit the `SUPABASE_SERVICE_ROLE_KEY` to version control
- Use environment variables for all Supabase configuration
- Regularly rotate your service role key
- Enable Row Level Security on all tables
- Use HTTPS in production

## Next Steps

After completing this setup:

1. Test file uploads to ensure storage policies work
2. Test API creation and verify data is stored correctly
3. Implement any additional business logic as needed
4. Set up monitoring and alerts in Supabase dashboard

For more information, refer to the [Supabase Documentation](https://supabase.com/docs).


