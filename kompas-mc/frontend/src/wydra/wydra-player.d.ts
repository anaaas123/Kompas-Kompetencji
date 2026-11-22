export type Poza = "stoi" | "prosi" | "sklada";
export type Stan = "machanie" | "podskok" | "proszenie" | "nasluchiwanie" | "skupienie" | "radosc" | "sennosc";
export const STATES: Record<Stan,{pose: Poza; label: string; ms: number}>;
export type Player = { draw(state: Stan, ms: number): void; dispose(): void };
export function makePlayer(canvas: HTMLCanvasElement, imageURL: string, pose: Poza, lidsURL: string): Promise<Player>;
