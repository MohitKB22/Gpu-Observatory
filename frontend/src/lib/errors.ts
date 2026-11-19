/** Human-readable title for a recorded inference error kind (see backend ProviderErrorKind). */
export function errorTitle(kind: string | null): string {
  switch (kind) {
    case 'timeout':
      return 'The endpoint timed out';
    case 'connection':
      return 'Could not reach the endpoint';
    case 'auth':
      return 'The endpoint rejected the credentials';
    case 'invalid_response':
      return 'The endpoint returned an unexpected response';
    case 'configuration':
      return 'The model is misconfigured';
    default:
      return 'The endpoint returned an error';
  }
}
