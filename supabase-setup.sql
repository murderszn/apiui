-- Supabase Setup SQL for ai-apiup backend
-- This file contains the SQL commands to set up the database schema and storage policies

-- Enable Row Level Security globally
ALTER DATABASE postgres SET row_security = on;

-- Create the apis table
CREATE TABLE IF NOT EXISTS public.apis (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    created_at timestamptz DEFAULT now() NOT NULL,
    user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    api_name text NOT NULL,
    endpoint_url text,
    file_path text,
    status text DEFAULT 'pending' CHECK (status IN ('pending', 'generating', 'deploying', 'active', 'failed')),
    deployment_metadata jsonb DEFAULT '{}'::jsonb
);

-- Enable Row Level Security on the apis table
ALTER TABLE public.apis ENABLE ROW LEVEL SECURITY;

-- Create policies for the apis table

-- Policy 1: Allow users to view their own APIs
CREATE POLICY "Users can view their own APIs" ON public.apis
    FOR SELECT
    USING (auth.uid() = user_id);

-- Policy 2: Allow users to create new APIs
CREATE POLICY "Users can create their own APIs" ON public.apis
    FOR INSERT
    WITH CHECK (auth.uid() = user_id);

-- Policy 3: Allow users to update their own APIs
CREATE POLICY "Users can update their own APIs" ON public.apis
    FOR UPDATE
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- Policy 4: Allow users to delete their own APIs
CREATE POLICY "Users can delete their own APIs" ON public.apis
    FOR DELETE
    USING (auth.uid() = user_id);

-- Create storage bucket for user uploads (this is done via Supabase Dashboard or API)
-- The bucket should be named 'user-uploads' and set to private

-- Storage policies for user-uploads bucket
-- These policies ensure users can only access their own uploaded files

-- Policy: Allow authenticated users to upload files
CREATE POLICY "Users can upload their own files" ON storage.objects
    FOR INSERT
    WITH CHECK (
        bucket_id = 'user-uploads'
        AND auth.role() = 'authenticated'
        AND (storage.foldername(name))[1] = auth.uid()::text
    );

-- Policy: Allow users to view and download their own files
CREATE POLICY "Users can view their own files" ON storage.objects
    FOR SELECT
    USING (
        bucket_id = 'user-uploads'
        AND auth.role() = 'authenticated'
        AND (storage.foldername(name))[1] = auth.uid()::text
    );

-- Policy: Allow users to update their own files
CREATE POLICY "Users can update their own files" ON storage.objects
    FOR UPDATE
    USING (
        bucket_id = 'user-uploads'
        AND auth.role() = 'authenticated'
        AND (storage.foldername(name))[1] = auth.uid()::text
    )
    WITH CHECK (
        bucket_id = 'user-uploads'
        AND auth.role() = 'authenticated'
        AND (storage.foldername(name))[1] = auth.uid()::text
    );

-- Policy: Allow users to delete their own files
CREATE POLICY "Users can delete their own files" ON storage.objects
    FOR DELETE
    USING (
        bucket_id = 'user-uploads'
        AND auth.role() = 'authenticated'
        AND (storage.foldername(name))[1] = auth.uid()::text
    );

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS apis_user_id_idx ON public.apis(user_id);
CREATE INDEX IF NOT EXISTS apis_status_idx ON public.apis(status);
CREATE INDEX IF NOT EXISTS apis_created_at_idx ON public.apis(created_at DESC);

-- Create a function to automatically set user_id on insert
CREATE OR REPLACE FUNCTION public.set_user_id()
RETURNS TRIGGER AS $$
BEGIN
    NEW.user_id = auth.uid();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Note: The trigger is not needed since we're using DEFAULT auth.uid() in the table definition
-- But keeping this for reference if needed for complex scenarios

-- Grant necessary permissions
GRANT USAGE ON SCHEMA public TO authenticated;
GRANT ALL ON public.apis TO authenticated;
GRANT ALL ON storage.objects TO authenticated;
GRANT ALL ON storage.buckets TO authenticated;

-- Insert some sample data for testing (optional)
-- This would be inserted by the application when APIs are created
-- INSERT INTO public.apis (user_id, api_name, endpoint_url, file_path, status)
-- VALUES ('user-uuid-here', 'Sample API', 'https://api.example.com', 'uploads/user-uuid/sample.csv', 'active');


