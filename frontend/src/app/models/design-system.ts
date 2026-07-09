export interface DesignSystem {
  colors: Record<string, string>;
  typography: {
    fontFamily: string;
    baseSize: string;
    headings: Record<'h1' | 'h2' | 'h3', string>;
  };
  spacing: Record<string, string>;
  borders: {
    radius: string;
    radiusLarge: string;
    radiusFull: string;
  };
  effects: {
    glassmorphism: {
      backgroundColor: string;
      backdropFilter: string;
      border: string;
    };
  };
}

