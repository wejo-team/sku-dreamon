export const mascotAvatarIds = [
  'skon',
  'arti',
  'dmo',
  'bart',
  'conver',
] as const;
export type MascotAvatarId = (typeof mascotAvatarIds)[number];

export const mascotAvatars = [
  { id: 'skon', name: '스콘' },
  { id: 'arti', name: '아티' },
  { id: 'dmo', name: '디모' },
  { id: 'bart', name: '비아트' },
  { id: 'conver', name: '컨버' },
] as const satisfies readonly { id: MascotAvatarId; name: string }[];

export const defaultMascotAvatarId: MascotAvatarId = 'skon';

export function mascotAvatarSource(id: MascotAvatarId) {
  return `/mascots/${id}.png`;
}
