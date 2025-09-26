

# AI-API-UP: Supabase Backend Specification

## 1. Project Goal

This document outlines the required backend setup for `ai-apiup.web.app` using Supabase. The objective is to create a robust and secure backend to manage user accounts, file uploads, and a multi-tenant database of user-generated APIs. This implementation will replace any existing client-side data management and resolve data persistence issues.

---

## Part 1: Supabase Configuration

### 1.1. User Management (Authentication)

**Objective:** Configure Supabase Auth to handle user sign-up, login, and identity.

* [ ] **Navigate to Authentication > Providers** in your Supabase project dashboard.
* [ ] **Enable Email Provider:** In the "Providers" list, enable the **Email** provider. This allows users to sign up with an email and password.
* [ ] **Review User Table:** Note that user data is automatically managed in the `auth.users` table. The `id` from this table will be used as the foreign key to link users to their resources.

### 1.2. File Storage for Uploads (Supabase Storage)

**Objective:** Create a secure, private storage bucket for user-uploaded flat files (CSV, JSON, etc.).

* [ ] **Navigate to the Storage section** in the dashboard and click  **Create a new bucket** .
* [ ] **Name the bucket `user-uploads`** .
* [ ] **Ensure the bucket is private.** The "Make this bucket public" checkbox must remain  **unchecked** .
* [ ] **Apply Security Policies:** Select the `user-uploads` bucket, go to the **Policies** tab, and create the following policies from scratch:
  * [ ] **Policy 1: Allow authenticated users to upload files.**
  * [ ] **Policy 2: Allow users to view and download their own files.**

### 1.3. Database for APIs List

**Objective:** Create a database table to store metadata for each user-generated API, secured with Row Level Security (RLS) to ensure data privacy.

* [ ] **Navigate to the Table Editor** and click  **New table** .
* [ ] **Name the table `apis`** .
* [ ] **Define Columns:**
  * `id`: `bigint` (Default, Primary Key)
  * `created_at`: `timestamptz` (Default value: `now()`)
  * `user_id`: `uuid` (Default value: `auth.uid()`, set up a Foreign Key relationship to `auth.users.id`)
  * `api_name`: `text` (A user-provided name for the API)
  * `endpoint_url`: `text` (The final URL of the deployed API)
  * `file_path`: `text` (The path to the source file in the `user-uploads` bucket)
  * `status`: `text` (e.g., 'active', 'deploying', 'failed')
* [ ] **Enable Row Level Security:** Once the table is created, click the **Enable RLS** button.
* [ ] **Create RLS Policies** for the `apis` table:
  * [ ] **Policy 1: Allow users to view their own APIs.**
  * [ ] **Policy 2: Allow users to create new APIs.**

---

## Part 2: Client-Side Integration

### 2.1. New Application Workflow

**Objective:** Implement the end-to-end logic connecting the front-end to the new Supabase backend.

1. **Authentication:** The user signs up or logs into the app using the Supabase client library.
2. **File Upload:** The user uploads their file. The front-end uploads it directly to the `user-uploads` Supabase Storage bucket.
3. **API Generation & Record Creation:** After your backend generates the API, the front-end inserts a new record into the `public.apis` table, storing the endpoint URL and file path. The `user_id` is handled automatically by the database policy.
4. **Displaying APIs:** The "My APIs" page queries the `apis` table. RLS ensures only the logged-in user's data is returned.

### 2.2. "My APIs" List Refactor

**Objective:** Replace all previous client-side logic for the API list with a direct and secure query to Supabase.

* [ ] **Initialize Supabase Client:** Ensure a single Supabase client is initialized and exported for use throughout your application. Use environment variables for your project URL and anon key.
* [ ] **Implement Supabase Query:** In the component responsible for displaying the "My APIs" list, replace all old data-fetching logic with the following Supabase query.
