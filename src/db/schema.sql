CREATE TYPE request_status AS ENUM ('pending', 'processing', 'done', 'failed');

CREATE TABLE requests (
    request_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    status request_status NOT NULL DEFAULT 'pending',
    raw_input TEXT,
    structured_text JSONB,
    results JSONB,
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE corrections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id UUID REFERENCES requests(request_id),
    original_text_span TEXT,
    model_code TEXT,
    coder_corrected_code TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
