/**
 * 通讯器顶上的公告细条（玩家端方案 7.1“公告”入口；320 宽下顶上一排已满，不加第五个分段）。
 * - 有未读：放最新的一条未读——标题一行、按级别着色（维护 / 通知 / 公告），点它去 /announcements；
 * - 全都读过：同一个位置收成安静的一行（不上底色、字变淡），仍能点进去重看——否则读完之后通讯器里就再也找不到公告；
 * - 没有公告、还在读、读失败、读不到（source = not_installed，不是“没有公告”）：一行都不占（出错只在公告页里说，不在通讯器里打扰）。
 * 已读按账号分开、每个账号按 slug + revision 记在本机（见 ./announcements.ts）；打开公告页时全部记为已读。
 */
import { Link } from "react-router";
import { Icon } from "@/shared/ui";
import { pickStripAnnouncement, severityOf } from "./announcements";
import { useAnnouncementFeed, useAnnouncementReadAccount, useAnnouncementReadMap } from "./useAnnouncements";
import "./announcements.css";

export function AnnouncementStrip() {
  const feed = useAnnouncementFeed();
  const read = useAnnouncementReadMap(useAnnouncementReadAccount());
  const data = feed.data;
  if (!data || data.source === "not_installed") return null;
  const picked = pickStripAnnouncement(data.announcements, read);
  if (!picked) return null;
  const { announcement, unread } = picked;
  const severity = severityOf(announcement.severity);
  return (
    <Link
      to="/announcements"
      className={`ps-announce-strip ${unread ? `ps-announce--${severity.tone}` : "ps-announce-strip--read"}`}
      data-unread={unread ? "true" : "false"}
      aria-label={unread ? `有新${severity.noun}：${announcement.title}` : `公告：${announcement.title}`}
    >
      <span className="ps-announce-tag">{unread ? severity.label : "公告"}</span>
      <span className="ps-announce-strip__title">{announcement.title}</span>
      {unread ? <span className="ps-announce-strip__dot" aria-hidden="true" /> : null}
      <Icon name="chevron" size={14} strokeWidth={2.2} className="ps-announce-strip__go" />
    </Link>
  );
}
