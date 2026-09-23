/**
 * 爪爪驾校的 fixture 数据（只用于 fixture 模式与比赛现场体验版，明确是演示数据）。
 * - 课程与场地：driving-school.json 由后端 scripts/gen_driving_fixtures.py 生成，前端不手改；
 * - 演示题：只有几道示例题，不是正式题库（正式题库与答案只在服务端，不进浏览器）。
 */
import offline from "./driving-school.json";
import type { SchoolCurriculum } from "@/shared/contracts";
import type { Course } from "@/features/driving_school/sim/types";

export interface DemoQuestion {
  question_id: string;
  kind: "choice" | "match" | "order";
  scene: string;
  topic_title: string;
  prompt: string;
  options: { option_id: string; label: string }[];
  targets: { target_id: string; label: string }[];
  group: string | null;
  group_title: string | null;
  story: string[];
  answer: { choice?: string; order?: string[]; matches?: Record<string, string> };
  explanation: string;
  pet_line: string;
}

export const DEMO_CURRICULUM = offline.curriculum as unknown as SchoolCurriculum;
export const DEMO_COURSES = offline.courses as unknown as Record<string, Course>;

export function demoCourse(item: string, variant: "a" | "b" = "a"): Course {
  return structuredClone(DEMO_COURSES[`${item}.${variant}`]);
}

const choice = (id: string, scene: string, topic: string, prompt: string, labels: string[], right: number, explanation: string, petLine: string): DemoQuestion => ({
  question_id: id,
  kind: "choice",
  scene,
  topic_title: topic,
  prompt,
  options: labels.map((label, i) => ({ option_id: `${id}.${i}`, label })),
  targets: [],
  group: null,
  group_title: null,
  story: [],
  answer: { choice: `${id}.${right}` },
  explanation,
  pet_line: petLine,
});

export const DEMO_QUESTIONS: Record<"s1" | "s4", DemoQuestion[]> = {
  s1: [
    choice("demo.s1.walk", "zebra_penguin", "礼让过街的居民（演示题）", "企鹅居民正走在斑马线上，小车来到路口，应该？", ["停在线前，等它走完", "从它身后绕过去", "按喇叭催它快点"], 0,
      "斑马线上有居民，就停在线前等它走完。", "这个我记住了，先让小企鹅过去。"),
    {
      question_id: "demo.s1.pre",
      kind: "order",
      scene: "car_check",
      topic_title: "出发前检查（演示题）",
      prompt: "准备出发前，把下面几步排好顺序",
      options: [
        { option_id: "demo.s1.pre.2", label: "调好后视镜" },
        { option_id: "demo.s1.pre.0", label: "绕车看一圈" },
        { option_id: "demo.s1.pre.3", label: "观察周围再起步" },
        { option_id: "demo.s1.pre.1", label: "坐好系上安全带" },
      ],
      targets: [],
      group: null,
      group_title: null,
      story: [],
      answer: { order: ["demo.s1.pre.0", "demo.s1.pre.1", "demo.s1.pre.2", "demo.s1.pre.3"] },
      explanation: "先看看车周围，再系安全带、调镜子，最后观察周围再起步。",
      pet_line: "绕车、系带、调镜、观察，再出发。",
    },
    {
      question_id: "demo.s1.signs",
      kind: "match",
      scene: "sign_board",
      topic_title: "停车让行（演示题）",
      prompt: "把两块标志放到它们该出现的地方",
      options: [
        { option_id: "demo.s1.signs.o1", label: "人行横道牌" },
        { option_id: "demo.s1.signs.o0", label: "“停”字牌" },
      ],
      targets: [
        { target_id: "demo.s1.signs.t0", label: "没有红绿灯的路口前" },
        { target_id: "demo.s1.signs.t1", label: "斑马线旁边" },
      ],
      group: null,
      group_title: null,
      story: [],
      answer: { matches: { "demo.s1.signs.t0": "demo.s1.signs.o0", "demo.s1.signs.t1": "demo.s1.signs.o1" } },
      explanation: "“停”字牌放在需要停车让行的路口，人行横道牌在斑马线旁。",
      pet_line: "每块牌子都有自己的位置。",
    },
  ],
  s4: [
    { ...choice("demo.s4.1", "phone_invite", "手机收到视频邀请（演示题）", "要不要马上看？", ["马上点开", "先不看，专心开车", "看一眼再说"], 1, "开车时不看视频，专心看路。", "开车的时候不看视频。"),
      group: "demo.s4", group_title: "手机收到视频邀请", story: ["正在开车，手机弹出：朋友邀请你一起看新上的动画片。"] },
    { ...choice("demo.s4.2", "phone_invite", "手机收到视频邀请（演示题）", "那这条邀请怎么处理？", ["等停好车再回复", "一边开一边打字回复", "把视频放在方向盘上看"], 0, "停好车再回复。", "停好车再回消息。"),
      group: "demo.s4", group_title: "手机收到视频邀请", story: ["正在开车，手机弹出：朋友邀请你一起看新上的动画片。"] },
  ],
};
