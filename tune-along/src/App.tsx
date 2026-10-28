import { useEffect } from 'react';
import { useRoute, navigate } from './app/router';
import { dismissNotice, initSession, live } from './app/session';
import { useStore } from './lib/store';
import { HelpView } from './ui/HelpView';
import { LibraryView, SongView } from './ui/LibraryView';
import { ListenView } from './ui/ListenView';
import { TunerView } from './ui/TunerView';
import { Icon } from './ui/widgets';

const TABS = [
  { path: 'listen', label: 'Listen', icon: 'listen' },
  { path: 'songs', label: 'Songs', icon: 'songs' },
  { path: 'tuner', label: 'Tuner', icon: 'tuner' },
  { path: 'help', label: 'Help', icon: 'help' },
];

function Notices() {
  const notices = useStore(live, (s) => s.notices);
  useEffect(() => {
    if (!notices.length) return;
    const t = setTimeout(() => dismissNotice(notices[0].at), notices[0].kind === 'error' ? 9000 : 6500);
    return () => clearTimeout(t);
  }, [notices]);
  return (
    <div className="notices" aria-live="polite">
      {notices.map((n) => (
        <div key={n.at} className={`notice ${n.kind}`}>
          <span>{n.text}</span>
          {n.songId && n.kind === 'learned' && <button className="btn small" onClick={() => { navigate(`/song/${n.songId}`); dismissNotice(n.at); }}>Open</button>}
          <button className="icon-btn" aria-label="Dismiss" onClick={() => dismissNotice(n.at)}><Icon name="x" size={16} /></button>
        </div>
      ))}
    </div>
  );
}

export default function App() {
  const route = useRoute();
  const listening = useStore(live, (s) => s.status === 'listening');
  useEffect(() => { void initSession(); }, []);
  const top = route[0] ?? 'listen';
  let view;
  if (top === 'song' && route[1]) view = <SongView id={route[1]} />;
  else if (top === 'songs') view = <LibraryView />;
  else if (top === 'tuner') view = <TunerView />;
  else if (top === 'help') view = <HelpView />;
  else view = <ListenView />;
  const activeTab = top === 'song' ? 'songs' : top;
  return (
    <div className="app">
      <header className="topbar no-print">
        <a className="brand" href="#/listen" aria-label="TuneAlong home">
          <img src="icons/icon.svg" alt="" width={30} height={30} />
          <span>Tune<b>Along</b></span>
        </a>
        <nav className="tabs-top" aria-label="Main">
          {TABS.map((t) => (
            <a key={t.path} href={`#/${t.path}`} className={activeTab === t.path ? 'on' : ''}>
              <Icon name={t.icon} size={18} /> {t.label}
              {t.path === 'listen' && listening && <span className="live-dot" aria-label="listening" />}
            </a>
          ))}
        </nav>
      </header>
      <main>{view}</main>
      <nav className="tabbar no-print" aria-label="Main">
        {TABS.map((t) => (
          <a key={t.path} href={`#/${t.path}`} className={activeTab === t.path ? 'on' : ''}>
            <Icon name={t.icon} size={22} />
            <span>{t.label}</span>
            {t.path === 'listen' && listening && <span className="live-dot" />}
          </a>
        ))}
      </nav>
      <Notices />
    </div>
  );
}
