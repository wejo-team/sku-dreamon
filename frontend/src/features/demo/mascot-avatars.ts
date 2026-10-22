/**
 * [참조 출처]
 * 1. design-reference/src/features/design-preview/mascot-avatars.ts - 마스코트 목록 원본
 * 2. docs/design/assets.md - 파워프렌즈 5종 이미지 출처
 * 3. docs/specs/profile.md#profile-image - 선택형 마스코트, 기본 스콘
 */

export const mascotAvatarIds = [
  'skon',
  'arti',
  'dmo',
  'bart',
  'conver',
] as const;
export type MascotAvatarId = (typeof mascotAvatarIds)[number];

// [출처 2] 마스코트 이름·이미지
export const mascotAvatars = [
  { id: 'skon', name: '스콘' },
  { id: 'arti', name: '아티' },
  { id: 'dmo', name: '디모' },
  { id: 'bart', name: '비아트' },
  { id: 'conver', name: '컨버' },
] as const satisfies readonly { id: MascotAvatarId; name: string }[];

// [출처 3] 기본 스콘
export const defaultMascotAvatarId: MascotAvatarId = 'skon';

export function mascotAvatarSource(id: MascotAvatarId) {
  return `/mascots/${id}.png`;
}
