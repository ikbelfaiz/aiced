import type { ClientRow } from './clients/model';

// Static fictional values from the supplied PDFs, for an explicitly labelled
// development-only visual comparison. Never written to the API or used as scoring rules.
export const previewClients: ClientRow[] = [
  { id: 'mock-1', name: 'Karim Ben Youssef', reference: 'CL-001248', kind: 'physical', segment: 'VIP', risk: 'Modéré', invested: 480000, products: 'SICAV · FCP · Bourse', score: 88, interaction: '29 sept. 2026', status: 'Actif' },
  { id: 'mock-2', name: 'Nadia Trabelsi', reference: 'CL-000986', kind: 'physical', segment: 'Particulier', risk: 'Prudent', invested: 125000, products: 'SICAV · FCP', score: 72, interaction: '20 juil. 2026', status: 'À relancer' },
  { id: 'mock-3', name: 'Atlas Industries', reference: 'CL-000842', kind: 'legal', segment: 'Institutionnel', risk: 'Prudent', invested: 2400000, products: 'SICAV', score: 94, interaction: '25 sept. 2026', status: 'Actif' },
  { id: 'mock-4', name: 'Sarra Mansour', reference: 'CL-001102', kind: 'physical', segment: 'VIP', risk: 'Dynamique', invested: 365000, products: 'FCP · Bourse', score: 85, interaction: '28 sept. 2026', status: 'Actif' },
  { id: 'mock-5', name: 'Yassine Haddad', reference: 'CL-001186', kind: 'physical', segment: 'AMEN BANK', risk: 'Modéré', invested: 78000, products: 'FCP AMEN CEA', score: 68, interaction: '24 sept. 2026', status: 'Actif' },
  { id: 'mock-6', name: 'Inès Cherif', reference: 'CL-000764', kind: 'physical', segment: 'Particulier', risk: 'Prudent', invested: 92000, products: 'SICAV AMEN', score: 61, interaction: '12 août 2026', status: 'À surveiller' },
  { id: 'mock-7', name: 'Meditech Services', reference: 'CL-001035', kind: 'legal', segment: 'Institutionnel', risk: 'Modéré', invested: 1150000, products: 'SICAV · FCP', score: 91, interaction: '30 sept. 2026', status: 'Actif' },
  { id: 'mock-8', name: 'Amine Gharbi', reference: 'CL-000658', kind: 'physical', segment: 'Particulier', risk: 'Dynamique', invested: 54000, products: 'Bourse', score: 57, interaction: '10 sept. 2026', status: 'Actif' },
];
export const previewTrend = [
  { month: 'Avr.', clients: 1000, activity: 180 }, { month: 'Mai', clients: 1075, activity: 220 },
  { month: 'Juin', clients: 1100, activity: 228 }, { month: 'Juil.', clients: 1175, activity: 265 },
  { month: 'Août', clients: 1250, activity: 290 }, { month: 'Sept.', clients: 1280, activity: 312 },
];
export const previewSegments = [
  { name: 'Particuliers', value: 762, color: '#2d8798' }, { name: 'VIP', value: 274, color: '#e27162' },
  { name: 'Institutionnels', value: 112, color: '#17263a' }, { name: 'Personnel AMEN BANK', value: 100, color: '#aebac8' },
];
