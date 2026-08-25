// 任务 → 对话的 kind 感知 auto-send 深链（/chat?q=...&send=1）。
// TodayCard 行动按钮与目标 kickoff CTA 共用同一套消息构造。
import type { OrchDailyTask } from "@/lib/types-modules";

type Tr = (key: string, fallback?: string) => string;

/** 渲染名：自定义标题优先，其次概念名，最后兜底「总结」。 */
export function taskDisplayName(task: OrchDailyTask, tr: Tr): string {
  return task.title.trim() || task.concept_name || tr("today.kind.summary");
}

/** kind 感知对话消息；无概念的自定义任务直接发标题。 */
export function taskChatMessage(task: OrchDailyTask, tr: Tr): string {
  const name = task.concept_name.trim();
  if (!name) return task.title.trim() || tr("task.msg.summary");
  switch (task.kind) {
    case "review":
      return tr("task.msg.review").replace("%c", name);
    case "practice":
      return tr("task.msg.practice").replace("%c", name);
    case "summary":
      return tr("task.msg.summary");
    default:
      return tr("task.msg.study").replace("%c", name);
  }
}

export function taskChatHref(task: OrchDailyTask, tr: Tr): string {
  return `/chat?q=${encodeURIComponent(taskChatMessage(task, tr))}&send=1`;
}

/** kind 感知的行动按钮文案（去学 / 去复习 / 去练 / 去总结）。 */
export function taskGoLabel(task: OrchDailyTask, tr: Tr): string {
  return tr(`task.go.${task.kind}`, tr("today.go"));
}
