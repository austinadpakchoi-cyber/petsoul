/**
 * 公告页 /announcements（通讯器 · 公告，二级页全屏，外面由 WorldGate 守；左上角回通讯器）。
 * - 列出全部公告，按生效时间倒序：级别、生效日期、标题、正文（按原文排，保留换行；纯文本，不当 HTML）、配图、链接；
 * - 链接：站内路径用 Link；http(s) 外链新窗口打开、带 rel="noopener noreferrer" 并写明“外部链接”和对方站点；其它一律不做成链接；
 * - 配图只用服务端给的站内地址，带说明文字（alt）；图读不出来（素材下架）就不显示这块；
 * - 打开这一页时，把当前所有公告记为已读（本机、记在当前账号下，按 slug + revision）；这次打开前没读过的标一个“新”；
 * - 状态：读取中 / 出错（可重试）/ 读不到（source = not_installed，温和说明“暂时不可用”，不说成“没有公告”）/ 空（“暂时没有公告”）；
 *   演示模式标“演示公告”（契约的 source 没有“演示”这一值，按 env.dataMode 判断，与卡包等页同一做法）。
 */
import { useEffect, useId, useState, type ReactNode } from "react";
import { Link } from "react-router";
import { env } from "@/shared/config/env";
import { DataOriginBadge, EmptyState, ErrorState, Icon, LoadingState, Page, TopBar } from "@/shared/ui";
import {
  announcementDay,
  announcementImageSrc,
  announcementLink,
  isUnread,
  markAnnouncementsRead,
  parseReadState,
  readKeyOf,
  readRawReadState,
  severityOf,
  sortAnnouncements,
  type Announcement,
} from "./announcements";
import { useAnnouncementFeed, useAnnouncementReadAccount } from "./useAnnouncements";
import "./announcements.css";

function AnnouncementImage({ src, title }: { src: string; title: string }) {
  const [broken, setBroken] = useState(false);
  if (broken) return null;
  return (
    <figure className="ps-announcement__figure">
      <img src={src} alt={`公告「${title}」的配图`} loading="lazy" decoding="async" onError={() => setBroken(true)} />
    </figure>
  );
}

function AnnouncementLinkView({ raw }: { raw: string | null }) {
  const link = announcementLink(raw);
  if (link.kind === "internal") {
    return (
      <Link className="ps-announcement__link" to={link.to}>
        查看详情
        <Icon name="chevron" size={14} strokeWidth={2.2} />
      </Link>
    );
  }
  if (link.kind === "external") {
    return (
      <a
        className="ps-announcement__link ps-announcement__link--external"
        href={link.href}
        target="_blank"
        rel="noopener noreferrer"
        aria-label={`外部链接：${link.host}（在新窗口打开）`}
      >
        <span className="ps-announcement__external">外部链接</span>
        <span className="ps-announcement__host">{link.host}</span>
      </a>
    );
  }
  return null;
}

function AnnouncementCard({ announcement, fresh }: { announcement: Announcement; fresh: boolean }) {
  const titleId = useId();
  const severity = severityOf(announcement.severity);
  const image = announcementImageSrc(announcement.image_url);
  const day = announcementDay(announcement.effective_at);
  return (
    <li>
      <article className={`ps-announcement ps-announce--${severity.tone}`} aria-labelledby={titleId} data-slug={announcement.slug}>
        <div className="ps-announcement__meta">
          <span className="ps-announce-tag">{severity.label}</span>
          {fresh ? <span className="ps-announcement__new">新</span> : null}
          {day ? <time dateTime={announcement.effective_at ?? undefined}>{day}</time> : null}
        </div>
        <h2 id={titleId} className="ps-announcement__title">
          {announcement.title}
        </h2>
        {announcement.body ? <p className="ps-announcement__body">{announcement.body}</p> : null}
        {image ? <AnnouncementImage key={image} src={image} title={announcement.title} /> : null}
        <AnnouncementLinkView raw={announcement.link} />
      </article>
    </li>
  );
}

export function AnnouncementsPage() {
  const feed = useAnnouncementFeed();
  const account = useAnnouncementReadAccount();
  const data = feed.data;
  /** 这次打开前没读过的（slug#revision）。只增不减：记为已读之后，“新”仍留到离开这一页。 */
  const [fresh, setFresh] = useState<ReadonlySet<string>>(() => new Set());

  useEffect(() => {
    if (!data || data.source === "not_installed" || data.announcements.length === 0) return;
    const before = parseReadState(readRawReadState(account));
    const newly = data.announcements.filter((announcement) => isUnread(announcement, before)).map(readKeyOf);
    if (newly.length) {
      setFresh((previous) => {
        const next = new Set(previous);
        for (const key of newly) next.add(key);
        return next;
      });
    }
    markAnnouncementsRead(account, data.announcements);
  }, [data, account]);

  let content: ReactNode;
  if (!data) {
    content = feed.isError ? (
      <ErrorState error={feed.error} onRetry={() => void feed.refetch()} />
    ) : (
      <LoadingState lines={2} label="正在取公告…" />
    );
  } else if (data.source === "not_installed") {
    // 读不到（后端没装运营后台），不是“没有公告”：温和说明，不给错误样式，也不写“暂时没有公告”。
    content = (
      <EmptyState icon="info" title="公告暂时不可用">
        过一会儿再来看看。
      </EmptyState>
    );
  } else if (data.announcements.length === 0) {
    content = (
      <EmptyState icon="mail" title="暂时没有公告">
        有新的通知时，会放在这里。
      </EmptyState>
    );
  } else {
    content = (
      <ul className="ps-announcements" aria-label="全部公告">
        {sortAnnouncements(data.announcements).map((announcement) => (
          <AnnouncementCard key={announcement.item_id} announcement={announcement} fresh={fresh.has(readKeyOf(announcement))} />
        ))}
      </ul>
    );
  }

  return (
    <Page bare className="ps-announcements-page">
      <TopBar
        title="公告"
        subtitle="来自 PetSoul 的通知"
        back="/communicator"
        right={env.dataMode === "fixture" ? <DataOriginBadge origin="fixture" label="演示公告" /> : undefined}
      />
      {content}
    </Page>
  );
}
