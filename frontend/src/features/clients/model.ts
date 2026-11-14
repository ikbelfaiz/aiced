import type { Party } from '../../lib/api';

export type ClientRow = {
  id: string; name: string; reference: string; kind: 'physical' | 'legal'; backendId?: string;
  segment?: string; risk?: string; invested?: number; products?: string; score?: number;
  interaction?: string; status?: string;
};
export function toClientRow(party: Party): ClientRow {
  return { id: party.id, backendId: party.id, name: party.display_name, reference: `ID AICED · ${party.id.slice(0, 8)}`, kind: party.kind };
}
export const formatNumber = (value: number) => new Intl.NumberFormat('fr-FR').format(value);
