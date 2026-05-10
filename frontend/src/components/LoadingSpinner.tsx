import styles from './LoadingSpinner.module.css'

interface Props {
  message?: string
}

export function LoadingSpinner({ message = 'Loading…' }: Props) {
  return (
    <div className={styles.wrapper} role="status" aria-live="polite">
      <div className={styles.spinner} aria-hidden="true" />
      <span className={styles.message}>{message}</span>
    </div>
  )
}
