import { Outlet } from 'react-router-dom'
import { NavBar } from '../components/NavBar'
import styles from './DashboardLayout.module.css'

export function DashboardLayout() {
  return (
    <div className={styles.layout}>
      <NavBar />
      <main className={styles.main}>
        <Outlet />
      </main>
    </div>
  )
}
