import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';

@Component({
  standalone: true,
  imports: [CommonModule],
  selector: 'app-generated-component',
  templateUrl: './generated.component.html',
  styleUrls: ['./generated.component.css'] })
export class GeneratedComponent {
  features = [
    { title: 'Fast', description: 'Blazing fast performance out of the box.' },
    { title: 'Secure', description: 'Enterprise‑grade security built in.' },
    { title: 'Beautiful', description: 'Stunning UI with zero effort.' },
  ];
}
