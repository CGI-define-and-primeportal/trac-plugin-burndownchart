$(document).ready(function(){

  // Expects date as a string in yyyy-mm-dd format. This is then converted
  // to a JS date object in the same yyyy-mm-dd format for the jqPlot library.
  window.dateFormat = function(date){
    split_date = date.split('-');
    // The month is zero indexed hence -1
    var formatted_date = $.datepicker.formatDate('yy-mm-dd', new Date(split_date[0], split_date[1] - 1, split_date[2]));
    return formatted_date
  };

  window.burndownChartData = new Array();
  for (i in burndowndata) {
    if (i == 'name') {
      var milestone_name = burndowndata['name'];
    }
    else if (i == 'start_date') {
      var milestone_start = burndowndata['start_date'];
    }
    else if (i == 'end_date') {
      var milestone_end = burndowndata['end_date'];
    }
    else if (i == 'total_hours') {
      var total_hours = burndowndata['total_hours'];
    }
    else if (i == 'hours_logged') {
      var hours_logged = burndowndata['hours_logged'];
    }
    else if (i == 'effort_units') {
      var effort_units = burndowndata['effort_units']
    }
    else {
      burndownChartData.push(dateFormat(burndowndata[i]));
    }
  }

  var sortedData = burndownChartData.sort() // To be chronological

  // Team Effort Data

    window.teamEffort = new Array();
    for (i in teameffortdata) {
      teamEffort.push([dateFormat(i), teameffortdata[i]])
    }

    window.idealCurve = new Array();
    for (i in idealcurvedata) {
      idealCurve.push([dateFormat(i), idealcurvedata[i]])
    }

  // Render the jqPlot burn down chart
  var sprintEffort = [[burndowndata['start_date'], total_hours], ['2013-07-15', 10], [burndowndata['end_date'], 0]];
  //var team_effort = [['2013-07-25', burndowndata['hours_logged'], ['2013-07-26', 20]]]
  var plot1 = $.jqplot('chart1', [sprintEffort, teamEffort, idealCurve], {
    //title: burndowndata['name'],
    axesDefaults: {
      tickRenderer: $.jqplot.CanvasAxisTickRenderer,
      tickOptions: {
        fontFamily: 'Open Sans',
        fontSize: '8pt'
      },
      labelOptions: {
        textColor: '#0066CC',
        fontFamily: 'Open Sans',
        fontSize: '10pt',
        fontWeight: 'normal'
      }
    },
    axes: {
      xaxis: {
        renderer:$.jqplot.DateAxisRenderer,
        tickOptions:{formatString: '%d %b'},
        label: 'Days in Milestone',
        min: burndowndata['start_date'],
        max: burndowndata['end_date'],
      },
      yaxis: {
        label: 'Effort (' + effort_units +')',
        min: 0,
        labelRenderer: $.jqplot.CanvasAxisLabelRenderer
      }
    }, 
    highlighter: {
      show: true, 
      tooltipAxes: 'both',
      sizeAdjust: 7.5,
      fadeTooltip: true,
      tooltipFadeSpeed: 'fast',
      tooltipAxes: 'xy',
      formatString: '%s - %s ' + effort_units,
      },
    series:[
            {color:'#5FAB78', label: 'Sprint effort'},
            {label: 'Team effort'},
            {label: 'Ideal effort', showMarker: false},
           ],
    legend: {
      show: true,
      }
  });
});