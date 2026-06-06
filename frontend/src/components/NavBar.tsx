import { Link, useLocation } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import styles from './NavBar.module.css'

export function NavBar() {
  const { logout, role, email } = useAuth()
  const location = useLocation()

  const isActive = (path: string) => location.pathname === path

  return (
    <nav className={styles.nav}>
      <div className={styles.brand}>
        <span className={styles.logo}>📊</span>
        <span className={styles.title}>AI Campaign Dashboard</span>
      </div>

      <div className={styles.links}>
        <Link
          to="/dashboard"
          className={`${styles.link} ${isActive('/dashboard') ? styles.active : ''}`}
        >
          Overview
        </Link>
        <Link
          to="/dashboard/create-campaign"
          className={`${styles.link} ${isActive('/dashboard/create-campaign') ? styles.active : ''}`}
        >
          Create
        </Link>
        <Link
          to="/dashboard/campaigns"
          className={`${styles.link} ${location.pathname.startsWith('/dashboard/campaigns') ? styles.active : ''}`}
        >
          Campaigns
        </Link>
        <Link
          to="/dashboard/alerts"
          className={`${styles.link} ${isActive('/dashboard/alerts') ? styles.active : ''}`}
        >
          Alerts
        </Link>
        <Link
          to="/dashboard/connect-facebook"
          className={`${styles.link} ${isActive('/dashboard/connect-facebook') ? styles.active : ''}`}
        >
          Connect Facebook
        </Link>
      </div>

      <div className={styles.user}>
        <span className={styles.roleTag} data-role={role}>
          {role}
        </span>
        {email && <span className={styles.email}>{email}</span>}
        <button className={styles.logoutBtn} onClick={logout}>
          Logout
        </button>
      </div>
    </nav>
  )
}
