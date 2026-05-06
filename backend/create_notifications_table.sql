-- Migration script to add telegram_notifications table
-- Run this SQL script on your Supabase database

CREATE TABLE IF NOT EXISTS public.telegram_notifications (
    id SERIAL PRIMARY KEY,
    phone VARCHAR(20) NOT NULL,
    notification_type VARCHAR(50) NOT NULL,
    message_data JSONB NOT NULL,
    sent BOOLEAN DEFAULT FALSE NOT NULL,
    sent_at TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_telegram_notifications_phone ON public.telegram_notifications(phone);
CREATE INDEX IF NOT EXISTS idx_telegram_notifications_sent ON public.telegram_notifications(sent);
CREATE INDEX IF NOT EXISTS idx_telegram_notifications_created_at ON public.telegram_notifications(created_at);
CREATE INDEX IF NOT EXISTS idx_telegram_notifications_type ON public.telegram_notifications(notification_type);

-- Comment for documentation
COMMENT ON TABLE public.telegram_notifications IS 'Queue for Telegram notifications (reminders, cancellations)';
COMMENT ON COLUMN public.telegram_notifications.notification_type IS 'Type: cancellation, reminder, etc.';
COMMENT ON COLUMN public.telegram_notifications.message_data IS 'JSON data with message details (name, start_time, etc.)';
