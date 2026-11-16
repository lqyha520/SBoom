// Batch size is independent of the provider request size. Keep image count in
// sync with app/models/image_generation.py, PDF pages with paper_storage.py.
export const MAX_WORKSHEET_IMAGES = 100
export const MAX_IMAGE_CONCURRENCY = 4
export const MAX_PAPERS_PER_RUN = 100
export const MAX_QUESTIONS_PER_TYPE = 100
export const MAX_QUESTIONS_PER_REQUEST = 30
export const MAX_ITEMS_PER_REQUEST = 10
export const MAX_PAPER_SECTIONS = 60
export const MAX_PAPER_QUESTIONS = 1500
export const MAX_WORKSHEET_PDF_PAGES = 40
export const MAX_WORKSHEET_PDF_BYTES = 32 * 1024 * 1024
export const MAX_WORKSHEET_ZIP_BYTES = 128 * 1024 * 1024

// A reading section belongs to one passage and cannot be split across calls.
export const sectionQuestionLimit = (type: string) => type === 'reading' ? MAX_QUESTIONS_PER_REQUEST : MAX_QUESTIONS_PER_TYPE
