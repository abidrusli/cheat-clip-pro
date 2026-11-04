import { useEffect, useState } from 'react';

type BeforeInstallPromptEvent = Event & {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>;
};

/**
 * Floating "Install App" button for browsers that support PWA installation.
 * Also shows a one-time hint on iOS, where installation is manual via Share.
 */
export default function PWAInstallPrompt() {
  const [deferred, setDeferred] = useState<BeforeInstallPromptEvent | null>(null);
  const [visible, setVisible] = useState(false);
  const [isIOS, setIsIOS] = useState(false);

  useEffect(() => {
    const ua = navigator.userAgent.toLowerCase();
    const ios = /iphone|ipad|ipod/.test(ua) && !(window as any).MSStream;
    setIsIOS(ios);

    // Don't show inside the native Android shell or the Electron desktop app.
    if ((window as any).Capacitor?.isNativePlatform?.()) return;
    if ((window as any).electronAPI?.isDesktop) return;
    if ((window as any).SKPDownloader || /SinyalAbidnetKliperPro/i.test(navigator.userAgent)) return;

    const standalone =
      window.matchMedia('(display-mode: standalone)').matches ||
      (navigator as any).standalone === true;

    const handler = (event: Event) => {
      event.preventDefault();
      setDeferred(event as BeforeInstallPromptEvent);
      setVisible(true);
    };

    window.addEventListener('beforeinstallprompt', handler);

    if (ios && !standalone && !localStorage.getItem('skp_ios_install_dismissed')) {
      setVisible(true);
    }

    return () => window.removeEventListener('beforeinstallprompt', handler);
  }, []);

  const dismiss = () => {
    setVisible(false);
    if (isIOS) localStorage.setItem('skp_ios_install_dismissed', '1');
  };

  const install = async () => {
    if (deferred) {
      await deferred.prompt();
      const choice = await deferred.userChoice;
      if (choice.outcome === 'accepted') setVisible(false);
      setDeferred(null);
      return;
    }
    if (isIOS) {
      window.alert(
        'Di iPhone/iPad: buka tombol Bagikan (Share) lalu pilih "Tambahkan ke Layar Utama" / "Add to Home Screen".'
      );
      dismiss();
    }
  };

  if (!visible) return null;

  return (
    <div
      style={{
        position: 'fixed',
        right: 16,
        bottom: 16,
        zIndex: 9999,
        display: 'flex',
        gap: 8,
        alignItems: 'center',
        background: 'linear-gradient(135deg,#7c3aed,#2563eb)',
        color: '#fff',
        padding: '10px 14px',
        borderRadius: 14,
        boxShadow: '0 8px 30px rgba(0,0,0,.35)',
        fontFamily: 'inherit',
      }}
    >
      <button
        type="button"
        onClick={install}
        style={{
          background: 'transparent',
          border: 0,
          color: '#fff',
          fontWeight: 700,
          fontSize: 14,
          cursor: 'pointer',
          padding: 0,
        }}
      >
        📲 Pasang / Install
      </button>
      <button
        type="button"
        onClick={dismiss}
        aria-label="Tutup"
        style={{
          background: 'rgba(255,255,255,.18)',
          border: 0,
          color: '#fff',
          borderRadius: 8,
          width: 24,
          height: 24,
          cursor: 'pointer',
          lineHeight: '24px',
          padding: 0,
        }}
      >
        ×
      </button>
    </div>
  );
}
