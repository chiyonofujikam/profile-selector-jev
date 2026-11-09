/** Use the product label in visible metadata and API error messages. */
export function modelText(value: string): string {
  return value.replace(/\bjev\b/gi, 'Decision model')
}

export function errorMessage(error: unknown): string {
  if (error instanceof Error) return error.message
  return 'Something went wrong. Please retry.'
}
