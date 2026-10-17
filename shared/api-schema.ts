// 自动生成：python scripts/generate_api_types.py；请修改后端模型后重新生成。
export interface ApiSchemas {
  "AdminCreateUser": { "password": string; "role"?: string; "username": string }
  "AdminLlmConfigIn": { "apiKey"?: string; "baseUrl"?: string; "id"?: (string | null); "maxTokens"?: number; "model"?: string; "timeout"?: number }
  "AdminProfileUpdate": { "avatar"?: (string | null); "new_password"?: (string | null); "nickname"?: (string | null); "revision": number; "username"?: (string | null) }
  "AdminUpdateUser": { "is_active"?: (boolean | null); "password"?: (string | null); "role"?: (string | null) }
  "ArchiveUpdate": { "favorite"?: (boolean | null); "folder_id"?: (string | null); "title"?: (string | null) }
  "AuthCapabilities": { "registration_enabled": boolean }
  "BannerInput": { "action_label"?: string; "image_fit"?: "contain" | "cover"; "is_visible"?: boolean; "kicker"?: string; "sort_order"?: number; "subtitle"?: string; "target_type"?: "none" | "keyword" | "category" | "subject" | "paper"; "target_value"?: string; "title": string }
  "BannerUpdate": { "action_label"?: string; "image_fit"?: "contain" | "cover"; "is_visible"?: boolean; "kicker"?: string; "revision": number; "sort_order"?: number; "subtitle"?: string; "target_type"?: "none" | "keyword" | "category" | "subject" | "paper"; "target_value"?: string; "title": string }
  "BatchGenerateRequest": { "difficulty"?: ApiSchemas["Difficulty"]; "grade": string; "items": Array<ApiSchemas["BatchItem"]>; "keyword": string; "previous_request_ids"?: Array<string>; "subject": string }
  "BatchGenerateResponse": { "request_id"?: (string | null); "sections"?: Array<ApiSchemas["GameResult"]> }
  "BatchItem": { "game_type": string; "question_count"?: number; "section_id"?: (string | null) }
  "BillInput": { "bill_date": string }
  "BulkTemplatesIn": { "templates": Array<{ [key: string]: unknown }> }
  "CardCreate": { "days": number; "expires_at"?: (number | null); "quantity"?: number }
  "CardRedeem": { "code": string }
  "CatalogBatch": { "action": "category" | "published" | "withdrawn" | "access" | "tags"; "category_id"?: string; "confirm_publication"?: boolean; "download_access"?: "inherit" | "free" | "vip"; "items": Array<ApiSchemas["RevisionItem"]>; "tag_ids"?: Array<string>; "view_access"?: "inherit" | "free" | "vip" }
  "CatalogCreate": { "category"?: string; "category_id"?: string; "description"?: string; "download_access"?: "inherit" | "free" | "vip"; "download_mode"?: "pdf" | "external"; "external_code"?: string; "external_url"?: string; "grade"?: string; "paper_id"?: string; "subject"?: string; "title"?: string; "view_access"?: "inherit" | "free" | "vip" }
  "CatalogFavorite": { "favorite": boolean }
  "CatalogRevision": { "confirm_publication"?: boolean; "note": string; "paper_id": string; "revision": number }
  "CatalogUpdate": { "category"?: string; "category_id"?: string; "confirm_publication"?: boolean; "description"?: string; "download_access"?: "inherit" | "free" | "vip"; "download_mode"?: "pdf" | "external"; "external_code"?: string; "external_url"?: string; "featured"?: boolean; "revision": number; "status": "draft" | "published" | "withdrawn"; "title": string; "view_access"?: "inherit" | "free" | "vip" }
  "CatalogWindow": { "ids": Array<string> }
  "CategoryInput": { "description"?: string; "icon"?: string; "is_visible"?: boolean; "name": string; "sort_order"?: number }
  "CategoryUpdate": { "description"?: string; "icon"?: string; "is_visible"?: boolean; "name": string; "revision": number; "sort_order"?: number }
  "ClosureInput": { "acknowledge": true; "reason"?: string }
  "ClosureReview": { "action": "approve" | "reject"; "confirm_deletion"?: boolean; "reply": string; "revision": number }
  "CodeInput": { "code": string }
  "ContentRequest": { "details"?: string; "grade"?: string; "subject"?: string; "title": string }
  "Credentials": { "password": string; "username": string }
  "DictionaryAdopt": { "kind": "grade" | "subject"; "values": Array<string> }
  "DictionaryInput": { "is_visible"?: boolean; "kind": "grade" | "subject" | "knowledge_point"; "label"?: string; "parent"?: string; "sort_order"?: number; "value": string }
  "DictionaryLinksUpdate": { "subject_ids"?: Array<string> }
  "DictionaryOrderItem": { "id": string; "revision": number }
  "DictionaryReorder": { "items": Array<ApiSchemas["DictionaryOrderItem"]>; "kind": "grade" | "subject" | "knowledge_point"; "parent"?: string }
  "DictionaryUpdate": { "is_visible"?: boolean; "label"?: string; "revision": number; "sort_order"?: number; "value": string }
  "Difficulty": "easy" | "medium" | "hard"
  "DocumentUpdate": { "body"?: string; "revision": number; "title": string }
  "EditionInput": { "confirm_publication"?: boolean; "kind": "student" | "answers"; "paper_id"?: (string | null); "revision": number }
  "ErrorResponse": { "detail"?: (string | null); "error": string }
  "FavoriteBatch": { "action": "remove" | "assign"; "group_id"?: (string | null); "ids": Array<string> }
  "FeedbackCreate": { "body": string; "catalog_id"?: (string | null); "kind": "correction" | "download" | "membership" | "other" }
  "FeedbackRequest": { "comment"?: (string | null); "game_id": string; "is_oob"?: boolean }
  "FeedbackUpdate": { "internal_note"?: string; "reply"?: string; "revision": number; "status": "pending" | "processing" | "resolved" | "closed" }
  "FolderInput": { "name": string }
  "GameResult": { "difficulty": string; "game_type": string; "grade": string; "missing_count"?: number; "pass_score"?: number; "passage"?: (string | null); "quality_warnings"?: Array<string>; "questions": Array<ApiSchemas["Question"]>; "request_id"?: (string | null); "section_id"?: (string | null); "subject": string; "topic": string; "total_score"?: number }
  "GameType": "quiz" | "fill_blank" | "match_pair" | "challenge" | "oral_math" | "reading" | "vertical_calc" | "recursive_calc" | "smart_calc" | "number_split" | "compare" | "true_false" | "word_problem"
  "GenerateRequest": { "difficulty"?: ApiSchemas["Difficulty"]; "game_type"?: ApiSchemas["GameType"]; "grade": string; "keyword": string; "question_count"?: number; "stream"?: boolean; "subject": string }
  "GroupAssignment": { "group_id"?: (string | null) }
  "GroupInput": { "name": string; "revision"?: number }
  "HTTPValidationError": { "detail"?: Array<ApiSchemas["ValidationError"]> }
  "HomeSettings": { "banner_mode"?: "welcome" | "operations"; "revision"?: number }
  "ImageModelConfig": { "apiKey"?: string; "baseUrl": string; "model": string; "requestMode"?: "auto" | "sync" | "async"; "responseFormat"?: "auto" | "b64_json" | "url"; "size"?: string; "timeout"?: number }
  "ImageModelProfile": { "apiKey"?: string; "baseUrl": string; "enabled"?: boolean; "id": string; "model": string; "name"?: string; "requestMode"?: "auto" | "sync" | "async"; "responseFormat"?: "auto" | "b64_json" | "url"; "size"?: string; "timeout"?: number }
  "ImageModelProfiles": { "models": Array<ApiSchemas["ImageModelProfile"]>; "revision": string }
  "ImageWorksheetItem": { "game_type": ApiSchemas["GameType"]; "question_count"?: (number | null) }
  "ImageWorksheetRequest": { "difficulty"?: ApiSchemas["Difficulty"]; "grade": string; "image_count"?: number; "image_index"?: number; "items"?: Array<ApiSchemas["ImageWorksheetItem"]>; "keyword"?: string; "requirements"?: string; "style"?: "playful" | "clean" | "black_white"; "subject": string }
  "KnowledgeScope": { "allowed": Array<string>; "books"?: Array<ApiSchemas["TextbookBook"]>; "catalog_revision"?: string; "forbidden": Array<string>; "grade": string; "semesters"?: ({ [key: string]: Array<string> } | null); "subject": string }
  "MembershipUpdate": { "is_active": boolean; "membership": "regular" | "vip"; "revision": number; "vip_expires_at"?: (number | null) }
  "MiniCredentials": { "password": string; "username": string }
  "MiniPasswordUpdate": { "current_password"?: string; "new_password": string }
  "MiniProfileUpdate": { "avatar"?: (string | null); "nickname"?: (string | null); "username"?: (string | null) }
  "MiniRegistration": { "password": string; "username": string }
  "NoticeInput": { "body"?: string; "ends_at"?: number; "is_visible"?: boolean; "level"?: "info" | "warning"; "placement"?: "popup" | "banner"; "starts_at"?: number; "title": string }
  "NoticeUpdate": { "body"?: string; "ends_at"?: number; "is_visible"?: boolean; "level"?: "info" | "warning"; "placement"?: "popup" | "banner"; "revision": number; "starts_at"?: number; "title": string }
  "OrderInput": { "plan_id": string; "plan_revision": number; "request_id": string }
  "PaperLabels": { "revision": number; "tag_ids"?: Array<string> }
  "PlanInput": { "days": number; "description"?: string; "is_active"?: boolean; "name": string; "price_fen": number; "revision"?: number; "sort_order"?: number }
  "Question": { "acceptable_answers"?: (Array<string> | null); "analysis"?: string; "answer": (string | number | number | Array<Array<number>>); "difficulty_level"?: (number | null); "expected_time_seconds"?: (number | null); "id"?: (number | null); "left"?: (number | string | null); "left_expr"?: (string | null); "left_items"?: (Array<string> | null); "options"?: (Array<string> | null); "quality_issues"?: Array<string>; "quality_status"?: "unchecked" | "passed" | "needs_review"; "right"?: (number | string | null); "right_expr"?: (string | null); "right_items"?: (Array<string> | null); "stem"?: string; "tags"?: Array<string>; "top"?: (number | string | null); "type"?: string }
  "RefundInput": { "reason": string }
  "RefundReview": { "action": "approve" | "reject"; "confirm_refund"?: boolean; "reply": string; "revision": number }
  "Registration": { "password": string; "username": string }
  "Renewal": { "days": number; "note"?: string; "revision": number }
  "ReorderInput": { "ids": Array<string> }
  "RequestResolution": { "catalog_id"?: (string | null); "reply"?: string; "revision": number; "status": "pending" | "planned" | "fulfilled" | "closed" }
  "RevisionItem": { "id": string; "revision": number }
  "SubscriptionGrant": { "request_id": string; "template_id": string }
  "SupportSettings": { "benefits"?: string; "email"?: string; "hours"?: string; "phone"?: string; "qr_url"?: string; "revision"?: number; "wechat"?: string }
  "TagInput": { "is_visible"?: boolean; "kind": "textbook" | "term" | "unit" | "knowledge"; "name": string; "revision"?: number; "sort_order"?: number }
  "TemplateIn": { "expected_revision"?: (number | null); "template": { [key: string]: unknown } }
  "TextModelProfile": { "apiKey"?: string; "baseUrl": string; "enabled"?: boolean; "id": string; "maxTokens"?: number; "model": string; "name"?: string; "timeout"?: number }
  "TextModelProfiles": { "models": Array<ApiSchemas["TextModelProfile"]>; "revision": string }
  "TextbookBook": { "id": string; "semester": string; "series": string; "source_url": string; "units": Array<ApiSchemas["TextbookUnit"]>; "verified_on": string }
  "TextbookUnit": { "page": number; "title": string; "topics"?: Array<string> }
  "TopicInput": { "description"?: string; "is_visible"?: boolean; "paper_ids"?: Array<string>; "revision"?: number; "sort_order"?: number; "title": string }
  "TypeAccessUpdate": { "download_access": "free" | "vip"; "revision": number; "view_access": "free" | "vip" }
  "UsageEvent": { "catalog_id"?: (string | null); "event_id": string; "kind": "active" | "download_ok" | "download_failed" }
  "ValidateRequest": { "grade": string; "question_content": string; "subject": string }
  "ValidateResult": { "is_oob": boolean; "oob_points"?: Array<string>; "request_id"?: (string | null); "suggestion"?: (string | null) }
  "ValidationError": { "ctx"?: { [key: string]: unknown }; "input"?: unknown; "loc": Array<(string | number)>; "msg": string; "type": string }
}

export interface ApiOperations {
  "POST /api/v1/admin/catalog/batch": { body: ApiSchemas["CatalogBatch"] }
  "POST /api/v1/admin/catalog/import": { body: unknown }
  "GET /api/v1/admin/catalog/papers": { body: unknown }
  "POST /api/v1/admin/catalog/papers": { body: ApiSchemas["CatalogCreate"] }
  "DELETE /api/v1/admin/catalog/papers/{catalog_id}": { body: unknown }
  "GET /api/v1/admin/catalog/papers/{catalog_id}": { body: unknown }
  "PUT /api/v1/admin/catalog/papers/{catalog_id}": { body: ApiSchemas["CatalogUpdate"] }
  "GET /api/v1/admin/catalog/papers/{catalog_id}/assets/{asset_id}": { body: unknown }
  "POST /api/v1/admin/catalog/papers/{catalog_id}/editions/import": { body: unknown }
  "GET /api/v1/admin/catalog/papers/{identifier}/edition-sources": { body: unknown }
  "PUT /api/v1/admin/catalog/papers/{identifier}/editions": { body: ApiSchemas["EditionInput"] }
  "PUT /api/v1/admin/catalog/papers/{identifier}/labels": { body: ApiSchemas["PaperLabels"] }
  "GET /api/v1/admin/catalog/papers/{identifier}/preview": { body: unknown }
  "POST /api/v1/admin/catalog/papers/{identifier}/revision": { body: ApiSchemas["CatalogRevision"] }
  "GET /api/v1/admin/catalog/sources": { body: unknown }
  "GET /api/v1/admin/catalog/summary": { body: unknown }
  "GET /api/v1/admin/catalog/tags": { body: unknown }
  "POST /api/v1/admin/catalog/tags": { body: ApiSchemas["TagInput"] }
  "DELETE /api/v1/admin/catalog/tags/{identifier}": { body: unknown }
  "PUT /api/v1/admin/catalog/tags/{identifier}": { body: ApiSchemas["TagInput"] }
  "GET /api/v1/admin/catalog/type-rules": { body: unknown }
  "PUT /api/v1/admin/catalog/type-rules/{question_type}": { body: ApiSchemas["TypeAccessUpdate"] }
  "GET /api/v1/admin/commerce/cards": { body: unknown }
  "POST /api/v1/admin/commerce/cards": { body: ApiSchemas["CardCreate"] }
  "POST /api/v1/admin/commerce/cards/{identifier}/disable": { body: unknown }
  "GET /api/v1/admin/commerce/orders": { body: unknown }
  "GET /api/v1/admin/commerce/orders/export": { body: unknown }
  "GET /api/v1/admin/commerce/orders/{identifier}": { body: unknown }
  "POST /api/v1/admin/commerce/orders/{identifier}/cancel": { body: unknown }
  "POST /api/v1/admin/commerce/orders/{identifier}/sync": { body: unknown }
  "GET /api/v1/admin/commerce/plans": { body: unknown }
  "POST /api/v1/admin/commerce/plans": { body: ApiSchemas["PlanInput"] }
  "PUT /api/v1/admin/commerce/plans/{identifier}": { body: ApiSchemas["PlanInput"] }
  "GET /api/v1/admin/commerce/reconciliations": { body: unknown }
  "POST /api/v1/admin/commerce/reconciliations": { body: ApiSchemas["BillInput"] }
  "GET /api/v1/admin/commerce/reconciliations/{identifier}": { body: unknown }
  "PUT /api/v1/admin/commerce/refunds/{identifier}": { body: ApiSchemas["RefundReview"] }
  "POST /api/v1/admin/commerce/refunds/{identifier}/sync": { body: unknown }
  "GET /api/v1/admin/engagement/closures": { body: unknown }
  "PUT /api/v1/admin/engagement/closures/{identifier}": { body: ApiSchemas["ClosureReview"] }
  "GET /api/v1/admin/engagement/delivery-status": { body: unknown }
  "GET /api/v1/admin/engagement/requests": { body: unknown }
  "PUT /api/v1/admin/engagement/requests/{identifier}": { body: ApiSchemas["RequestResolution"] }
  "GET /api/v1/admin/experience/analytics": { body: unknown }
  "GET /api/v1/admin/experience/feedback": { body: unknown }
  "PUT /api/v1/admin/experience/feedback/{identifier}": { body: ApiSchemas["FeedbackUpdate"] }
  "GET /api/v1/admin/experience/support": { body: unknown }
  "PUT /api/v1/admin/experience/support": { body: ApiSchemas["SupportSettings"] }
  "GET /api/v1/admin/experience/topics": { body: unknown }
  "POST /api/v1/admin/experience/topics": { body: ApiSchemas["TopicInput"] }
  "DELETE /api/v1/admin/experience/topics/{identifier}": { body: unknown }
  "PUT /api/v1/admin/experience/topics/{identifier}": { body: ApiSchemas["TopicInput"] }
  "GET /api/v1/admin/feedbacks": { body: unknown }
  "DELETE /api/v1/admin/image-config": { body: unknown }
  "GET /api/v1/admin/image-config": { body: unknown }
  "PUT /api/v1/admin/image-config": { body: (ApiSchemas["ImageModelProfiles"] | ApiSchemas["ImageModelConfig"]) }
  "DELETE /api/v1/admin/llm-config": { body: unknown }
  "GET /api/v1/admin/llm-config": { body: unknown }
  "PUT /api/v1/admin/llm-config": { body: (ApiSchemas["TextModelProfiles"] | ApiSchemas["AdminLlmConfigIn"]) }
  "GET /api/v1/admin/logs": { body: unknown }
  "GET /api/v1/admin/mini-users": { body: unknown }
  "POST /api/v1/admin/mini-users": { body: ApiSchemas["MiniRegistration"] }
  "GET /api/v1/admin/mini-users/{identifier}/events": { body: unknown }
  "POST /api/v1/admin/mini-users/{identifier}/renew": { body: ApiSchemas["Renewal"] }
  "DELETE /api/v1/admin/mini-users/{user_id}": { body: unknown }
  "PATCH /api/v1/admin/mini-users/{user_id}": { body: ApiSchemas["AdminProfileUpdate"] }
  "PUT /api/v1/admin/mini-users/{user_id}": { body: ApiSchemas["MembershipUpdate"] }
  "GET /api/v1/admin/mini-users/{user_id}/avatar/{version}": { body: unknown }
  "GET /api/v1/admin/site/analytics": { body: unknown }
  "GET /api/v1/admin/site/banners": { body: unknown }
  "POST /api/v1/admin/site/banners": { body: ApiSchemas["BannerInput"] }
  "DELETE /api/v1/admin/site/banners/{banner_id}": { body: unknown }
  "PUT /api/v1/admin/site/banners/{banner_id}": { body: ApiSchemas["BannerUpdate"] }
  "DELETE /api/v1/admin/site/banners/{banner_id}/image": { body: unknown }
  "GET /api/v1/admin/site/banners/{banner_id}/image": { body: unknown }
  "PUT /api/v1/admin/site/banners/{banner_id}/image": { body: unknown }
  "GET /api/v1/admin/site/categories": { body: unknown }
  "POST /api/v1/admin/site/categories": { body: ApiSchemas["CategoryInput"] }
  "PUT /api/v1/admin/site/categories/order": { body: ApiSchemas["ReorderInput"] }
  "DELETE /api/v1/admin/site/categories/{category_id}": { body: unknown }
  "PUT /api/v1/admin/site/categories/{category_id}": { body: ApiSchemas["CategoryUpdate"] }
  "GET /api/v1/admin/site/dictionary": { body: unknown }
  "POST /api/v1/admin/site/dictionary": { body: ApiSchemas["DictionaryInput"] }
  "POST /api/v1/admin/site/dictionary/adopt": { body: ApiSchemas["DictionaryAdopt"] }
  "GET /api/v1/admin/site/dictionary/links": { body: unknown }
  "PUT /api/v1/admin/site/dictionary/links/{grade_id}": { body: ApiSchemas["DictionaryLinksUpdate"] }
  "POST /api/v1/admin/site/dictionary/reorder": { body: ApiSchemas["DictionaryReorder"] }
  "GET /api/v1/admin/site/dictionary/unlisted": { body: unknown }
  "DELETE /api/v1/admin/site/dictionary/{item_id}": { body: unknown }
  "PUT /api/v1/admin/site/dictionary/{item_id}": { body: ApiSchemas["DictionaryUpdate"] }
  "GET /api/v1/admin/site/documents": { body: unknown }
  "PUT /api/v1/admin/site/documents/{key}": { body: ApiSchemas["DocumentUpdate"] }
  "GET /api/v1/admin/site/home-settings": { body: unknown }
  "PUT /api/v1/admin/site/home-settings": { body: ApiSchemas["HomeSettings"] }
  "GET /api/v1/admin/site/notices": { body: unknown }
  "POST /api/v1/admin/site/notices": { body: ApiSchemas["NoticeInput"] }
  "DELETE /api/v1/admin/site/notices/{notice_id}": { body: unknown }
  "PUT /api/v1/admin/site/notices/{notice_id}": { body: ApiSchemas["NoticeUpdate"] }
  "GET /api/v1/admin/stats": { body: unknown }
  "POST /api/v1/admin/test-llm": { body: (ApiSchemas["AdminLlmConfigIn"] | null) }
  "GET /api/v1/admin/users": { body: unknown }
  "POST /api/v1/admin/users": { body: ApiSchemas["AdminCreateUser"] }
  "DELETE /api/v1/admin/users/{user_id}": { body: unknown }
  "PUT /api/v1/admin/users/{user_id}": { body: ApiSchemas["AdminUpdateUser"] }
  "GET /api/v1/admin/users/{user_id}/templates": { body: unknown }
  "GET /api/v1/admin/users/{user_id}/templates/{tpl_id}": { body: unknown }
  "GET /api/v1/auth/capabilities": { body: unknown }
  "POST /api/v1/auth/login": { body: ApiSchemas["Credentials"] }
  "POST /api/v1/auth/logout": { body: unknown }
  "GET /api/v1/auth/me": { body: unknown }
  "POST /api/v1/auth/register": { body: ApiSchemas["Registration"] }
  "GET /api/v1/catalog/papers": { body: unknown }
  "GET /api/v1/catalog/papers/{catalog_id}": { body: unknown }
  "GET /api/v1/catalog/papers/{catalog_id}/assets/{asset_id}": { body: unknown }
  "POST /api/v1/catalog/papers/{catalog_id}/download": { body: unknown }
  "PUT /api/v1/catalog/papers/{catalog_id}/favorite": { body: ApiSchemas["CatalogFavorite"] }
  "GET /api/v1/catalog/summary": { body: unknown }
  "POST /api/v1/catalog/window": { body: ApiSchemas["CatalogWindow"] }
  "POST /api/v1/feedback": { body: ApiSchemas["FeedbackRequest"] }
  "POST /api/v1/generate": { body: ApiSchemas["GenerateRequest"] }
  "POST /api/v1/generate-batch": { body: ApiSchemas["BatchGenerateRequest"] }
  "POST /api/v1/generate-image": { body: ApiSchemas["ImageWorksheetRequest"] }
  "POST /api/v1/generate/stream": { body: ApiSchemas["GenerateRequest"] }
  "GET /api/v1/image-generation/assets/{asset_id}": { body: unknown }
  "GET /api/v1/image-generation/options": { body: unknown }
  "POST /api/v1/image-generation/prompt": { body: ApiSchemas["ImageWorksheetRequest"] }
  "GET /api/v1/library/assets/{asset_id}": { body: unknown }
  "GET /api/v1/library/folders": { body: unknown }
  "POST /api/v1/library/folders": { body: ApiSchemas["FolderInput"] }
  "DELETE /api/v1/library/folders/{folder_id}": { body: unknown }
  "PATCH /api/v1/library/folders/{folder_id}": { body: ApiSchemas["FolderInput"] }
  "PUT /api/v1/library/folders/{folder_id}": { body: ApiSchemas["FolderInput"] }
  "GET /api/v1/library/papers": { body: unknown }
  "POST /api/v1/library/papers": { body: unknown }
  "DELETE /api/v1/library/papers/{paper_id}": { body: unknown }
  "GET /api/v1/library/papers/{paper_id}": { body: unknown }
  "PATCH /api/v1/library/papers/{paper_id}": { body: ApiSchemas["ArchiveUpdate"] }
  "PUT /api/v1/library/papers/{paper_id}": { body: ApiSchemas["ArchiveUpdate"] }
  "PUT /api/v1/library/papers/{paper_id}/files": { body: unknown }
  "GET /api/v1/library/summary": { body: unknown }
  "GET /api/v1/me/generations/{request_id}": { body: unknown }
  "DELETE /api/v1/me/templates": { body: unknown }
  "GET /api/v1/me/templates": { body: unknown }
  "PUT /api/v1/me/templates": { body: ApiSchemas["TemplateIn"] }
  "POST /api/v1/me/templates/bulk": { body: ApiSchemas["BulkTemplatesIn"] }
  "GET /api/v1/me/usage": { body: unknown }
  "DELETE /api/v1/mini/closure": { body: unknown }
  "GET /api/v1/mini/closure": { body: unknown }
  "POST /api/v1/mini/closure": { body: ApiSchemas["ClosureInput"] }
  "POST /api/v1/mini/events": { body: ApiSchemas["UsageEvent"] }
  "GET /api/v1/mini/favorite-groups": { body: unknown }
  "POST /api/v1/mini/favorite-groups": { body: ApiSchemas["GroupInput"] }
  "PUT /api/v1/mini/favorite-groups/papers/{catalog_id}": { body: ApiSchemas["GroupAssignment"] }
  "DELETE /api/v1/mini/favorite-groups/{identifier}": { body: unknown }
  "PUT /api/v1/mini/favorite-groups/{identifier}": { body: ApiSchemas["GroupInput"] }
  "POST /api/v1/mini/favorites/batch": { body: ApiSchemas["FavoriteBatch"] }
  "GET /api/v1/mini/feedback": { body: unknown }
  "POST /api/v1/mini/feedback": { body: ApiSchemas["FeedbackCreate"] }
  "GET /api/v1/mini/feedback/{identifier}": { body: unknown }
  "DELETE /api/v1/mini/history": { body: unknown }
  "POST /api/v1/mini/history/{catalog_id}": { body: unknown }
  "POST /api/v1/mini/login": { body: ApiSchemas["CodeInput"] }
  "POST /api/v1/mini/login-password": { body: ApiSchemas["MiniCredentials"] }
  "POST /api/v1/mini/login-public": { body: ApiSchemas["CodeInput"] }
  "POST /api/v1/mini/logout": { body: unknown }
  "GET /api/v1/mini/me": { body: unknown }
  "PATCH /api/v1/mini/me": { body: ApiSchemas["MiniProfileUpdate"] }
  "PUT /api/v1/mini/me": { body: ApiSchemas["MiniProfileUpdate"] }
  "POST /api/v1/mini/me/avatar": { body: unknown }
  "GET /api/v1/mini/me/avatar/{version}": { body: unknown }
  "GET /api/v1/mini/membership/plans": { body: unknown }
  "POST /api/v1/mini/membership/redeem": { body: ApiSchemas["CardRedeem"] }
  "GET /api/v1/mini/message-subscription": { body: unknown }
  "POST /api/v1/mini/message-subscription": { body: ApiSchemas["SubscriptionGrant"] }
  "GET /api/v1/mini/messages": { body: unknown }
  "POST /api/v1/mini/messages/read-all": { body: unknown }
  "POST /api/v1/mini/messages/{identifier}/read": { body: unknown }
  "GET /api/v1/mini/orders": { body: unknown }
  "POST /api/v1/mini/orders": { body: ApiSchemas["OrderInput"] }
  "GET /api/v1/mini/orders/{identifier}": { body: unknown }
  "POST /api/v1/mini/orders/{identifier}/cancel": { body: unknown }
  "POST /api/v1/mini/orders/{identifier}/pay": { body: unknown }
  "POST /api/v1/mini/orders/{identifier}/refund": { body: ApiSchemas["RefundInput"] }
  "POST /api/v1/mini/orders/{identifier}/sync": { body: unknown }
  "POST /api/v1/mini/password": { body: ApiSchemas["MiniPasswordUpdate"] }
  "POST /api/v1/mini/refunds/{identifier}/sync": { body: unknown }
  "POST /api/v1/mini/register": { body: ApiSchemas["MiniRegistration"] }
  "GET /api/v1/mini/requests": { body: unknown }
  "POST /api/v1/mini/requests": { body: ApiSchemas["ContentRequest"] }
  "GET /api/v1/mini/requests/{identifier}": { body: unknown }
  "POST /api/v1/payments/wechat/notify": { body: unknown }
  "POST /api/v1/payments/wechat/refund-notify": { body: unknown }
  "GET /api/v1/scope": { body: unknown }
  "GET /api/v1/scope/available": { body: unknown }
  "GET /api/v1/site/banners/{banner_id}/image": { body: unknown }
  "GET /api/v1/site/catalog-tags": { body: unknown }
  "GET /api/v1/site/documents/{key}": { body: unknown }
  "GET /api/v1/site/home": { body: unknown }
  "GET /api/v1/site/support": { body: unknown }
  "GET /api/v1/site/topics": { body: unknown }
  "POST /api/v1/validate": { body: ApiSchemas["ValidateRequest"] }
  "GET /health": { body: unknown }
  "GET /health/detail": { body: unknown }
  "GET /readyz": { body: unknown }
}
